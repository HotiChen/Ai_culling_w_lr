"""L1 style extraction: develop settings -> clustered presets -> XMP.

We turn each image's develop adjustments into a numeric feature vector,
cluster keepers into *k* representative looks with a small dependency-free
k-means, pick the medoid of each cluster as the preset, and also emit a
median "signature" preset summarizing the whole body of work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.sax.saxutils import quoteattr

import numpy as np

from photovault.core.catalog.reader import CatalogImage
from photovault.settings import StyleSettings

# The crs-style keys that define a "look". We standardize on the 2012 process
# names where Lightroom has both legacy and 2012 variants.
STYLE_KEYS: tuple[str, ...] = (
    "Exposure2012",
    "Contrast2012",
    "Highlights2012",
    "Shadows2012",
    "Whites2012",
    "Blacks2012",
    "Clarity2012",
    "Vibrance",
    "Saturation",
    "Temperature",
    "Tint",
)


@dataclass
class Preset:
    name: str
    params: dict[str, float]
    support: int = 0  # how many images fall in this cluster

    def to_xmp(self) -> str:
        return preset_to_xmp(self)


@dataclass
class StyleResult:
    presets: list[Preset] = field(default_factory=list)
    signature: Preset | None = None  # median across all keepers
    n_samples: int = 0


def _feature_vector(img: CatalogImage) -> np.ndarray | None:
    """Build a STYLE_KEYS vector; None if the image has no usable adjustments."""
    p = img.develop.params
    if not p:
        return None
    vec = np.array([float(p.get(k, 0.0)) for k in STYLE_KEYS], dtype=np.float64)
    # Skip all-zero vectors (no meaningful develop work).
    if not np.any(vec):
        return None
    return vec


def _standardize(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = matrix.mean(axis=0)
    std = matrix.std(axis=0)
    std_safe = np.where(std == 0, 1.0, std)
    return (matrix - mean) / std_safe, mean, std_safe


def _kmeans(
    data: np.ndarray, k: int, iters: int, seed: int
) -> tuple[np.ndarray, np.ndarray]:
    """Tiny k-means. Returns (labels, centroids). Pure numpy, no sklearn."""
    rng = np.random.default_rng(seed)
    n = data.shape[0]
    k = min(k, n)
    # k-means++-ish seeding: first center random, rest farthest-point.
    centers = [data[rng.integers(n)]]
    for _ in range(1, k):
        dists = np.min(
            [np.sum((data - c) ** 2, axis=1) for c in centers], axis=0
        )
        probs = dists / dists.sum() if dists.sum() > 0 else None
        idx = rng.choice(n, p=probs) if probs is not None else rng.integers(n)
        centers.append(data[idx])
    centroids = np.array(centers)

    labels = np.zeros(n, dtype=int)
    for _ in range(iters):
        dists = np.linalg.norm(data[:, None, :] - centroids[None, :, :], axis=2)
        new_labels = dists.argmin(axis=1)
        if np.array_equal(new_labels, labels) and _ > 0:
            labels = new_labels
            break
        labels = new_labels
        for ci in range(k):
            members = data[labels == ci]
            if len(members):
                centroids[ci] = members.mean(axis=0)
    return labels, centroids


def extract_style(images: list[CatalogImage], cfg: StyleSettings) -> StyleResult:
    """Cluster develop settings into presets + a median signature."""
    vectors: list[np.ndarray] = []
    for img in images:
        v = _feature_vector(img)
        if v is not None:
            vectors.append(v)

    if not vectors:
        return StyleResult(presets=[], signature=None, n_samples=0)

    raw = np.vstack(vectors)
    n_samples = raw.shape[0]

    # Median signature in ORIGINAL units.
    sig_params = {k: round(float(v), 3) for k, v in zip(STYLE_KEYS, np.median(raw, axis=0))}
    signature = Preset(name="signature", params=sig_params, support=n_samples)

    std_data, mean, std = _standardize(raw)
    k = min(cfg.n_presets, n_samples)
    labels, _ = _kmeans(std_data, k, cfg.kmeans_iters, cfg.random_seed)

    presets: list[Preset] = []
    for ci in range(k):
        members_mask = labels == ci
        members = raw[members_mask]
        if len(members) == 0:
            continue
        # Medoid: the member closest to the cluster centroid (standardized space).
        std_members = std_data[members_mask]
        centroid = std_members.mean(axis=0)
        medoid_idx = int(np.argmin(np.linalg.norm(std_members - centroid, axis=1)))
        medoid = members[medoid_idx]
        params = {k_: round(float(v), 3) for k_, v in zip(STYLE_KEYS, medoid)}
        presets.append(Preset(name=f"look_{ci + 1}", params=params, support=int(len(members))))

    # Most-supported look first.
    presets.sort(key=lambda p: p.support, reverse=True)
    for i, p in enumerate(presets, 1):
        p.name = f"look_{i}"

    return StyleResult(presets=presets, signature=signature, n_samples=n_samples)


# --------------------------------------------------------------------------- #
# XMP export (Lightroom / Camera Raw develop-preset sidecar format)
# --------------------------------------------------------------------------- #
def preset_to_xmp(preset: Preset) -> str:
    attrs = "\n".join(
        f'      crs:{key}={quoteattr(_fmt_num(val))}'
        for key, val in preset.params.items()
    )
    return (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="PhotoVault">\n'
        ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '  <rdf:Description rdf:about=""\n'
        '    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"\n'
        '    crs:Version="15.0"\n'
        f'    crs:PresetType="Normal"\n'
        f'    crs:ClusterGroup="PhotoVault"\n'
        f'    crs:Name={quoteattr(preset.name)}\n'
        f"{attrs}>\n"
        "  </rdf:Description>\n"
        " </rdf:RDF>\n"
        "</x:xmpmeta>\n"
    )


def _fmt_num(val: float) -> str:
    """Format a number for XMP: integers without trailing ``.0``."""
    if float(val).is_integer():
        return str(int(val))
    return f"{val:.3f}".rstrip("0").rstrip(".")
