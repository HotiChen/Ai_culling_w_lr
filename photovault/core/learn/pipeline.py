"""The M1 learning pipeline: a folder of ``.lrcat`` files -> a Taste Profile.

This is the orchestration layer that ties together catalog reading (L1/L2),
style clustering, label export and profile persistence. Pixel-level L3
learning (taste_vector, classifier) is added in M2.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from photovault.core.catalog.cull_logic import Label, compute_stats, label_for
from photovault.core.catalog.labels import LabelRow, build_rows, write_csv
from photovault.core.catalog.reader import (
    CatalogImage,
    find_catalogs,
    find_icloud_lrcat_placeholders,
    iter_images,
    open_ro,
)
from photovault.core.catalog.style import extract_style
from photovault.core.features.clip_embed import Embedder
from photovault.core.judge import GemmaJudge, JudgeUnavailable
from photovault.core.learn.classifier import KeepRejectModel, train_classifier
from photovault.core.learn.taste import compute_taste_vector
from photovault.core.learn.vectorstore import get_vectorstore
from photovault.core.preview import extract_preview, find_preview
from photovault.core.profile.models import ProfileMeta, Thresholds
from photovault.core.profile.store import PROFILE_LAYOUT, save_profile
from photovault.settings import Settings


@dataclass
class LearnReport:
    name: str
    profile_dir: Path
    n_catalogs: int
    n_images: int
    n_keepers: int
    n_rejects: int
    n_presets: int
    llm_used: bool
    llm_note: str = ""
    # M2 pixel stage.
    pixels_used: bool = False
    n_embedded: int = 0
    pixels_note: str = ""
    # Catalogs skipped for having no curation signal (no picks/ratings/colors).
    n_skipped: int = 0
    skipped: list = field(default_factory=list)  # [{"catalog": str, "reason": str}]
    log: list = field(default_factory=list)  # human-readable log lines


@dataclass
class _PixelResult:
    taste_vector: np.ndarray | None
    classifier: KeepRejectModel | None
    embeddings: list[tuple[str, np.ndarray]]  # (id, embedding) for keepers
    sharpness_floor: float | None
    note: str


def _read_all_images(catalogs: list[Path]) -> list[CatalogImage]:
    images: list[CatalogImage] = []
    for cat in catalogs:
        conn = open_ro(cat)
        try:
            images.extend(iter_images(conn))
        finally:
            conn.close()
    return images


def _train_metadata_classifier(rows):
    """Train a keep/reject classifier from labeled rows using metadata features
    only (no pixels). Returns a model, or None if it can't be trained (fewer
    than two classes, or scikit-learn unavailable)."""
    labeled = [r for r in rows if r.label != Label.UNLABELED.value]
    if len(labeled) < 2:
        return None
    train_rows = [{"label": r.label} for r in labeled]
    train_feats = [
        {
            "iso": r.iso,
            "aperture_f": r.aperture_f,
            "focal_length": r.focal_length,
            "shutter_seconds": r.shutter_seconds,
            "burst_position": r.burst_position,
        }
        for r in labeled
    ]
    try:
        return train_classifier(train_rows, train_feats)
    except Exception:
        return None  # e.g. scikit-learn not installed


def has_curation_signal(images: list[CatalogImage]) -> bool:
    """True if any image carries a pick flag, a star rating, or a color label.

    A catalog with none of these has no keep/reject signal to learn from, so it
    is skipped (with a log entry) during learning.
    """
    for im in images:
        if im.pick != 0:
            return True
        if im.rating is not None and im.rating > 0:
            return True
        if im.color_label:
            return True
    return False


def catalog_label_stats(images: list[CatalogImage]) -> dict:
    """Per-catalog curation breakdown: star ratings, color labels, pick flags."""
    ratings = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    colors: dict[str, int] = {}
    flags = 0
    rejects = 0
    for im in images:
        r = im.rating or 0
        ratings[r if r in ratings else 0] += 1
        if im.color_label:
            colors[im.color_label] = colors.get(im.color_label, 0) + 1
        if im.pick == 1:
            flags += 1
        elif im.pick == -1:
            rejects += 1
    return {
        "ratings": ratings,
        "colors": colors,
        "flags": flags,
        "rejects": rejects,
        "n_images": len(images),
    }


def read_catalogs_filtered(
    catalogs: list[Path],
    progress=None,
) -> tuple[list[CatalogImage], list[Path], list[tuple[Path, str]]]:
    """Read images per catalog, skipping ones with no curation signal.

    Returns ``(images, kept_catalogs, skipped)`` where *skipped* is a list of
    ``(catalog_path, reason)`` for catalogs that were left out. If *progress* is
    given it is called once per catalog with a dict describing the catalog just
    read (name, label histogram, kept/skip decision) so callers can stream live
    progress.
    """
    images: list[CatalogImage] = []
    kept: list[Path] = []
    skipped: list[tuple[Path, str]] = []
    total = len(catalogs)
    for i, cat in enumerate(catalogs):
        conn = open_ro(cat)
        try:
            cat_images = list(iter_images(conn))
        finally:
            conn.close()
        stats = catalog_label_stats(cat_images)
        if not cat_images:
            decision, reason = False, "no images"
            skipped.append((cat, reason))
        elif not has_curation_signal(cat_images):
            decision, reason = False, "no picks / star ratings / color labels"
            skipped.append((cat, reason))
        else:
            decision, reason = True, ""
            images.extend(cat_images)
            kept.append(cat)
        if progress is not None:
            progress({
                "phase": "catalog",
                "index": i + 1,
                "total": total,
                "name": cat.name,
                "path": str(cat),
                "kept": decision,
                "reason": reason,
                "stats": stats,
                "running_images": len(images),
            })
    return images, kept, skipped


def collect_catalogs(catalog_folder: "str | Path | list") -> list[Path]:
    """Find every ``.lrcat`` under one or more root folders (deduped, sorted).

    Accepts a single folder or a list of folders so the caller can learn from
    several catalog roots at once. Duplicate catalogs (the same file reachable
    from overlapping roots) are collapsed by resolved path.
    """
    if isinstance(catalog_folder, (str, Path)):
        roots: list = [catalog_folder]
    else:
        roots = list(catalog_folder)

    catalogs: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        for cat in find_catalogs(root):
            resolved = cat.resolve()
            if resolved not in seen:
                seen.add(resolved)
                catalogs.append(cat)
    return catalogs


def collect_icloud_placeholders(catalog_folder: "str | Path | list") -> list[Path]:
    """iCloud-evicted ``.lrcat`` placeholders under one or more roots (deduped)."""
    if isinstance(catalog_folder, (str, Path)):
        roots: list = [catalog_folder]
    else:
        roots = list(catalog_folder)
    out: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        for ph in find_icloud_lrcat_placeholders(root):
            resolved = ph.resolve()
            if resolved not in seen:
                seen.add(resolved)
                out.append(ph)
    return out


def _decode_preview(data: bytes) -> np.ndarray | None:
    """Decode preview JPEG bytes to an RGB array (lazy Pillow)."""
    try:
        import io

        from PIL import Image  # lazy: only when pixels are actually processed
    except ImportError:
        return None
    try:
        return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
    except Exception:
        return None


def _resolve_embedder(embedder: Embedder | None) -> tuple[Embedder | None, str]:
    """Return an embedder + note. If None, try to build OpenClipEmbedder lazily."""
    if embedder is not None:
        return embedder, ""
    try:
        from photovault.core.features.clip_embed import OpenClipEmbedder

        # Importing open_clip/torch happens on first use; probe availability now.
        import importlib.util

        if importlib.util.find_spec("open_clip") is None:
            return None, "no embedder available (open-clip-torch not installed)"
        return OpenClipEmbedder(), ""
    except ImportError:
        return None, "no embedder available (open-clip-torch not installed)"


def _run_pixel_stage(
    images: list[CatalogImage],
    rows: list[LabelRow],
    preview_cache: Path,
    embedder: Embedder,
) -> _PixelResult:
    """Compute keeper embeddings -> taste_vector, train classifier, gather vecs.

    Locates each image's preview by base name in *preview_cache*; missing
    previews are skipped. Sharpness is folded into the classifier features.
    """
    from photovault.core.features.sharpness import sharpness_score

    by_id = {im.id_local: im for im in images}
    keeper_embeds: list[np.ndarray] = []
    keeper_ids: list[str] = []
    train_rows: list[dict] = []
    train_feats: list[dict] = []
    sharp_keep: list[float] = []
    n_embedded = 0

    for row in rows:
        if row.label == Label.UNLABELED.value:
            continue
        img = by_id.get(row.id_local)
        if img is None:
            continue
        preview = find_preview(preview_cache, img.base_name)
        if preview is None:
            continue
        data = extract_preview(preview)
        if data is None:
            continue
        arr = _decode_preview(data)
        if arr is None:
            continue

        sharp = sharpness_score(arr)
        emb = np.asarray(embedder.embed_image(arr), dtype=np.float32)
        n_embedded += 1

        feat = {
            "sharpness": sharp,
            "iso": row.iso,
            "aperture_f": row.aperture_f,
            "focal_length": row.focal_length,
            "shutter_seconds": row.shutter_seconds,
            "burst_position": row.burst_position,
        }
        train_rows.append({"label": row.label})
        train_feats.append(feat)

        if row.label == Label.KEEP.value:
            keeper_embeds.append(emb)
            keeper_ids.append(str(row.id_local))
            sharp_keep.append(sharp)

    if n_embedded == 0:
        return _PixelResult(None, None, [], None, "no previews found in cache")

    taste = compute_taste_vector(keeper_embeds) if keeper_embeds else None
    classifier = train_classifier(train_rows, train_feats)
    # A conservative sharpness floor: the 10th percentile of keeper sharpness.
    floor = float(np.percentile(sharp_keep, 10)) if sharp_keep else None

    return _PixelResult(
        taste_vector=taste,
        classifier=classifier,
        embeddings=list(zip(keeper_ids, keeper_embeds)),
        sharpness_floor=floor,
        note=f"embedded {n_embedded} previews",
    )


def learn_from_folder(
    catalog_folder: "str | Path | list",
    name: str,
    settings: Settings,
    use_llm: bool = True,
    preview_cache: str | Path | None = None,
    embedder: Embedder | None = None,
    judge=None,
    progress=None,
) -> LearnReport:
    """Run stage A and persist the profile. Returns a :class:`LearnReport`.

    *catalog_folder* is a single folder OR a list of folders; all ``.lrcat``
    files found under any of them are learned from together.

    *judge* is an optional GemmaJudge-compatible object (must implement
    ``write_profile(name, stats) -> str``).  When None and the LLM is
    enabled, a real :class:`GemmaJudge` is constructed lazily.  Pass an
    explicit object (e.g. a FakeJudge) to avoid any network calls in tests.
    """
    def _emit(event: dict) -> None:
        if progress is not None:
            progress(event)

    catalogs = collect_catalogs(catalog_folder)
    icloud = collect_icloud_placeholders(catalog_folder)
    if not catalogs and not icloud:
        raise ValueError(f"no .lrcat files found under {catalog_folder}")

    # Scan summary first so the user can see every subfolder was covered.
    log: list[str] = [
        f"scanned {len(catalogs)} .lrcat across all subfolders"
        + (f"; {len(icloud)} more are in iCloud (not downloaded)" if icloud else "")
    ]
    _emit({"phase": "scan", "n_catalogs": len(catalogs), "n_icloud": len(icloud)})

    # Skip catalogs with no curation signal (no picks/ratings/colors), logging each.
    images, kept_catalogs, skipped = read_catalogs_filtered(catalogs, progress=progress)
    for cat, reason in skipped:
        log.append(f"skipped {cat.name} — {reason}")

    # iCloud-evicted catalogs can't be opened; surface them as skipped too.
    for ph in icloud:
        original = ph.name.lstrip(".")[: -len(".icloud")]
        skipped.append((ph, "in iCloud — not downloaded to this Mac"))
        log.append(f"skipped {original} — in iCloud; download it then re-learn")

    if not images:
        extra = (
            f" ({len(icloud)} catalog(s) are in iCloud and not downloaded — "
            "download them or turn off 'Optimize Mac Storage', then re-learn)"
            if icloud
            else ""
        )
        raise ValueError(
            "every catalog was skipped (no picks / star ratings / color labels); "
            "nothing to learn from" + extra
        )

    # L2 stats + labels.
    _emit({"phase": "stats", "n_images": len(images)})
    stats = compute_stats(images, settings.cull)
    rows = build_rows(images, settings.cull)
    n_keepers = sum(1 for r in rows if r.label == Label.KEEP.value)
    n_rejects = sum(1 for r in rows if r.label == Label.REJECT.value)

    # Always train a metadata keep/reject classifier from the labeled rows, so
    # even a no-pixels (web) learn produces a real taste model — culling can then
    # score by your historical aperture/ISO/focal/burst-position decisions
    # instead of falling back to a gate-only pass. The pixel stage (if it runs)
    # trains a richer classifier that overrides this one.
    meta_classifier = _train_metadata_classifier(rows)

    # L1 style presets.
    _emit({"phase": "style"})
    style = extract_style(images, settings.style)

    # Build persisted models.
    summary = stats.summary()
    thresholds = Thresholds(
        keep_rate=summary["keep_rate"],
        aperture_f=summary["aperture_f"],
        iso=summary["iso"],
        focal_length=summary["focal_length"],
        burst_keep_rate=summary["bursts"]["burst_keep_rate"],
        keep_position_mean=summary["bursts"]["keep_position_mean"],
        keep_rating=settings.cull.keep_rating,
        reject_rating=settings.cull.reject_rating,
        burst_gap_seconds=settings.cull.burst_gap_seconds,
    )
    meta = ProfileMeta(
        name=name,
        source_catalogs=[str(c) for c in kept_catalogs],
        n_images=len(images),
        n_keepers=n_keepers,
        n_rejects=n_rejects,
        n_presets=len(style.presets),
    )

    # Optional LLM rule-book (Gemma). Falls back gracefully if unavailable.
    # Use the injected judge when provided; otherwise build one lazily.
    profile_md: str | None = None
    llm_used = False
    llm_note = ""
    if use_llm and settings.llm.enabled:
        _emit({"phase": "gemma"})
        active_judge = judge if judge is not None else GemmaJudge(settings.llm)
        try:
            llm_stats = {**summary, "presets": [p.params for p in style.presets]}
            profile_md = active_judge.write_profile(name, llm_stats)
            llm_used = True
        except JudgeUnavailable as exc:
            llm_note = f"LLM unavailable, wrote placeholder profile.md ({exc})"
    else:
        llm_note = "LLM skipped (--no-llm or disabled)"

    # Optional M2 pixel stage: previews -> embeddings -> taste_vector + classifier.
    pixels_used = False
    n_embedded = 0
    pixels_note = ""
    pixel: _PixelResult | None = None
    if preview_cache is None:
        pixels_note = "pixel stage skipped (no preview cache provided)"
    else:
        emb, emb_note = _resolve_embedder(embedder)
        if emb is None:
            pixels_note = emb_note
        else:
            pixel = _run_pixel_stage(images, rows, Path(preview_cache), emb)
            n_embedded = len(pixel.embeddings)
            pixels_note = pixel.note
            if n_embedded > 0 or pixel.classifier is not None:
                pixels_used = True
                if pixel.sharpness_floor is not None:
                    thresholds.sharpness_floor = pixel.sharpness_floor

    # Write labels CSV to a temp file, then fold into the profile bundle.
    _emit({"phase": "save"})
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = write_csv(rows, Path(tmp) / "labels.csv")
        profile_dir = save_profile(
            profiles_dir=settings.profiles_dir,
            name=name,
            meta=meta,
            thresholds=thresholds,
            presets=style.presets,
            signature=style.signature,
            profile_md=profile_md,
            labels_csv=csv_path,
            taste_vector=pixel.taste_vector if pixel else None,
            classifier=(
                pixel.classifier
                if (pixel and pixel.classifier is not None)
                else meta_classifier
            ),
        )

    # Populate the vector store under the profile's chroma/ dir.
    if pixel and pixel.embeddings:
        store = get_vectorstore(profile_dir / PROFILE_LAYOUT["chroma_dir"])
        ids = [i for i, _ in pixel.embeddings]
        vecs = [v for _, v in pixel.embeddings]
        store.add(ids=ids, vecs=vecs, metas=[{"id_local": i} for i in ids])

    return LearnReport(
        name=name,
        profile_dir=profile_dir,
        n_catalogs=len(kept_catalogs),
        n_images=len(images),
        n_keepers=n_keepers,
        n_rejects=n_rejects,
        n_presets=len(style.presets),
        llm_used=llm_used,
        llm_note=llm_note,
        pixels_used=pixels_used,
        n_embedded=n_embedded,
        pixels_note=pixels_note,
        n_skipped=len(skipped),
        skipped=[{"catalog": str(c), "reason": r} for c, r in skipped],
        log=log,
    )
