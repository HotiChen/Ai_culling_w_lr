"""Stage-B orchestration (M3): score a new photo folder with a learned profile.

``apply_to_folder`` ties the engine + dedup + export together:

1. scan the folder for image files and read each one's capture time (EXIF),
2. group them into bursts by capture-time proximity (same gap logic as stage A),
3. compute per-image features — sharpness, blink, CLIP embedding, pHash,
4. score (technical gate + taste blend + bands), then dedup per burst,
5. export: XMP sidecars (always), an HTML report, optional foldering.

Everything heavy is lazy or injectable: pass an ``embedder`` and ``blink_fn`` to
avoid touching torch/mediapipe. The pipeline degrades gracefully — a profile
without a taste_vector/classifier falls back to a gate-only pass (with a note),
and a missing embedder simply drops the taste-similarity term.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from photovault.core.catalog.cull_logic import parse_capture_time
from photovault.core.export.report import write_report
from photovault.core.export.foldering import sort_into_folders
from photovault.core.export.xmp import write_sidecar
from photovault.core.features.clip_embed import Embedder
from photovault.core.features.exif import read_capture_time, read_exif
from photovault.core.profile.store import load_profile
from photovault.core.score.dedup import dedup_bursts
from photovault.core.score.engine import KEEP, MAYBE, REJECT, ScoreResult, score_features
from photovault.settings import Settings

# Extensions we treat as scorable photos in a stage-B folder.
_IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp",
    ".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf", ".rw2", ".orf",
}

# A blink function maps an RGB array -> True / False / None (no face).
BlinkFn = Callable[[np.ndarray], "bool | None"]


@dataclass
class ApplyReport:
    """Outcome of a stage-B run: bucket counts + output paths + notes."""

    profile: str
    n_images: int
    n_keep: int
    n_maybe: int
    n_reject: int
    results: list[ScoreResult] = field(default_factory=list)
    report_path: Path | None = None
    sorted_dir: Path | None = None
    notes: list[str] = field(default_factory=list)


def _scan_images(folder: Path) -> list[Path]:
    return sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in _IMAGE_EXTS
    )


def _group_bursts(paths: list[Path], gap_seconds: float) -> dict[str, int]:
    """Assign a burst id to each path by capture-time proximity.

    Mirrors :func:`cull_logic.group_bursts`: files within *gap_seconds* of the
    previous frame share a burst; un-timed files each become their own burst.
    Returns ``{path_str: burst_id}``.
    """
    timed: list[tuple[object, Path]] = []
    untimed: list[Path] = []
    for p in paths:
        ts = parse_capture_time(read_capture_time(p))
        if ts is None:
            untimed.append(p)
        else:
            timed.append((ts, p))

    timed.sort(key=lambda x: x[0])  # type: ignore[index, return-value]
    assignment: dict[str, int] = {}
    burst_id = 0
    last_ts = None
    for ts, p in timed:
        if last_ts is not None and (ts - last_ts).total_seconds() > gap_seconds:
            burst_id += 1
        assignment[str(p)] = burst_id
        last_ts = ts
    # Each un-timed file gets its own fresh burst id.
    for p in untimed:
        burst_id += 1
        assignment[str(p)] = burst_id
    return assignment


def _decode_image(path: Path) -> np.ndarray | None:
    """Load a photo to an RGB array (lazy Pillow); ``None`` if it can't load."""
    try:
        from PIL import Image  # lazy
    except ImportError:
        return None
    try:
        with Image.open(path) as img:
            return np.asarray(img.convert("RGB"))
    except Exception:
        return None


def _resolve_embedder(embedder: Embedder | None) -> tuple[Embedder | None, str]:
    """Use the injected embedder, else try OpenClip lazily; note if unavailable."""
    if embedder is not None:
        return embedder, ""
    import importlib.util

    if importlib.util.find_spec("open_clip") is None:
        return None, "no embedder available — taste-similarity term skipped"
    from photovault.core.features.clip_embed import OpenClipEmbedder

    return OpenClipEmbedder(), ""


def _first_preset_xmp(preset_files: list[Path]) -> str | None:
    """Pick a develop preset to embed in every sidecar (M3: the top/first look).

    Prefer a non-signature look; fall back to whatever is present. Per-image best
    matching is deferred to a later milestone.
    """
    looks = [p for p in preset_files if p.stem != "signature"]
    chosen = (looks or preset_files)
    if not chosen:
        return None
    try:
        return chosen[0].read_text(encoding="utf-8")
    except OSError:
        return None


def apply_to_folder(
    photo_folder: str | Path,
    profile_name: str,
    settings: Settings,
    embedder: Embedder | None = None,
    blink_fn: BlinkFn | None = None,
    hash_fn: Callable[[np.ndarray], int] | None = None,
    sharpness_fn: Callable[[np.ndarray], float] | None = None,
    report: bool = True,
    sort_dir: str | Path | None = None,
) -> ApplyReport:
    """Run stage B over *photo_folder* using profile *profile_name*."""
    folder = Path(photo_folder)
    profile = load_profile(settings.profiles_dir, profile_name)
    cfg = settings.score
    notes: list[str] = []

    paths = _scan_images(folder)
    bursts = _group_bursts(paths, settings.cull.burst_gap_seconds)

    # Resolve the (injectable) feature backends. Sharpness/phash default to the
    # real, light implementations; blink/embedder are injected by tests.
    if sharpness_fn is None:
        from photovault.core.features.sharpness import sharpness_score as sharpness_fn
    if hash_fn is None:
        from photovault.core.features.phash import phash as hash_fn

    emb, emb_note = _resolve_embedder(embedder)
    if emb_note:
        notes.append(emb_note)
    if profile.taste_vector is None and emb is not None:
        notes.append("profile has no taste_vector — taste-similarity term skipped")
    if profile.classifier is None and profile.taste_vector is None:
        notes.append("M1-only profile — gate-only scoring (no taste model)")

    # --- Per-image features --------------------------------------------------- #
    items: list[dict] = []
    sharpness: dict[str, float] = {}
    blink: dict[str, bool | None] = {}
    hashes: dict[str, int] = {}
    for p in paths:
        iid = p.stem
        arr = _decode_image(p)
        if arr is None:
            notes.append(f"could not decode {p.name}")
            continue
        sharpness[iid] = float(sharpness_fn(arr))
        blink[iid] = blink_fn(arr) if blink_fn is not None else None
        hashes[iid] = int(hash_fn(arr))
        ex = read_exif(p)
        embedding = (
            np.asarray(emb.embed_image(arr), dtype=np.float32)
            if (emb is not None and profile.taste_vector is not None)
            else None
        )
        items.append(
            {
                "id": iid,
                "path": str(p),
                "burst_id": bursts.get(str(p), 0),
                "embedding": embedding,
                "features": {
                    "iso": ex.iso,
                    "aperture_f": ex.aperture_f,
                    "focal_length": ex.focal_length,
                    "shutter_seconds": ex.shutter_seconds,
                },
            }
        )

    # --- Score + dedup -------------------------------------------------------- #
    results = score_features(
        items=items,
        sharpness=sharpness,
        blink=blink,
        classifier=profile.classifier,
        taste_vector=profile.taste_vector,
        sharpness_floor=profile.thresholds.sharpness_floor,
        cfg=cfg,
    )
    results = dedup_bursts(
        results, hashes, profile.thresholds.burst_keep_rate, cfg
    )

    # --- Export --------------------------------------------------------------- #
    preset_xmp = _first_preset_xmp(profile.preset_files)
    for r in results:
        write_sidecar(r, preset_xmp=preset_xmp)

    report_path: Path | None = None
    if report:
        report_path = write_report(results, folder / "photovault_report.html")

    sorted_dir: Path | None = None
    if sort_dir is not None:
        sorted_dir = Path(sort_dir)
        sort_into_folders(results, sorted_dir)

    n_keep = sum(1 for r in results if r.decision == KEEP)
    n_maybe = sum(1 for r in results if r.decision == MAYBE)
    n_reject = sum(1 for r in results if r.decision == REJECT)

    return ApplyReport(
        profile=profile_name,
        n_images=len(results),
        n_keep=n_keep,
        n_maybe=n_maybe,
        n_reject=n_reject,
        results=results,
        report_path=report_path,
        sorted_dir=sorted_dir,
        notes=notes,
    )
