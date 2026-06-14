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
    # How many maybe items the LLM arbitrated (0 when LLM is disabled/unavailable).
    n_arbitrated: int = 0
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


def _arbitrate_maybe(
    results: list,
    judge,
    profile_md: str | None,
    settings: Settings,
    no_llm: bool,
    notes: list[str],
) -> int:
    """Arbitrate the ``maybe`` bucket in-place using *judge*.

    Returns the count of items actually decided by the LLM.  Mutates
    *results* and *notes*.  Never raises — any failure leaves the item as
    ``maybe`` and appends a note.

    Decision tree:
    1. ``no_llm=True`` -> skip, add note, return 0.
    2. ``settings.llm.enabled=False`` and no explicit judge -> skip, add note, 0.
    3. ``judge`` is None -> try to build a real GemmaJudge lazily.
    4. Call ``judge.arbitrate`` for each maybe item; on ``JudgeUnavailable``
       during the first call, abort the loop and add a note.
    """
    maybe_items = [r for r in results if r.decision == MAYBE]
    if not maybe_items:
        return 0

    if no_llm:
        notes.append("LLM arbitration skipped (--no-llm)")
        return 0

    # Resolve the judge: use the injected one, or build a lazy real one.
    active_judge = judge
    if active_judge is None:
        if not settings.llm.enabled:
            notes.append("LLM arbitration skipped (llm.enabled=False in settings)")
            return 0
        # Lazy construction of the real GemmaJudge; import is local to keep core/ clean.
        from photovault.core.judge.ollama_client import GemmaJudge
        active_judge = GemmaJudge(settings.llm)

    rule_book = profile_md or ""
    n_arbitrated = 0

    for r in maybe_items:
        try:
            from photovault.core.judge.ollama_client import JudgeUnavailable
            verdict = active_judge.arbitrate(r.path, rule_book)
        except JudgeUnavailable as exc:
            notes.append(f"LLM judge unavailable during arbitration: {exc}")
            return n_arbitrated  # stop arbitrating; leave remaining as maybe

        # Apply the verdict: keep -> KEEP, else -> REJECT.
        r.decision = KEEP if verdict.keep else REJECT
        r.reasons.append(f"gemma: {verdict.reason}")
        n_arbitrated += 1

    return n_arbitrated


def _stars(score: "float | None") -> int:
    """Map a 0..1 taste score to a 0..5 star rating (gate-only -> 0)."""
    if score is None:
        return 0
    return max(0, min(5, round(float(score) * 5)))


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
    judge=None,
    no_llm: bool = False,
    progress=None,
) -> ApplyReport:
    """Run stage B over *photo_folder* using profile *profile_name*.

    *judge* is an optional GemmaJudge-compatible object (must implement
    ``arbitrate(image_path, rule_book) -> Verdict``). When None and the LLM
    is enabled in settings (and *no_llm* is False), a real GemmaJudge is
    constructed lazily. Pass ``no_llm=True`` or set ``settings.llm.enabled=False``
    to skip arbitration entirely — maybe items stay as maybe.

    *progress* is an optional callback invoked with per-photo / per-phase event
    dicts (scan / photo / dedup / arbitrate / export) so callers can stream a
    live view of which photo is being scored and where it landed.
    """
    def _emit(event: dict) -> None:
        if progress is not None:
            progress(event)

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

    # --- Per-image features + live per-photo scoring -------------------------- #
    items: list[dict] = []
    sharpness: dict[str, float] = {}
    blink: dict[str, bool | None] = {}
    hashes: dict[str, int] = {}
    results: list[ScoreResult] = []
    total = len(paths)
    _emit({"phase": "scan", "n_photos": total})
    for i, p in enumerate(paths):
        iid = p.stem
        arr = _decode_image(p)
        if arr is None:
            notes.append(f"could not decode {p.name}")
            _emit({
                "phase": "photo", "index": i + 1, "total": total,
                "name": p.name, "band": None, "stars": 0, "score": None,
                "skipped": True, "reason": "could not decode",
            })
            continue
        sh = float(sharpness_fn(arr))
        bl = blink_fn(arr) if blink_fn is not None else None
        sharpness[iid] = sh
        blink[iid] = bl
        hashes[iid] = int(hash_fn(arr))
        ex = read_exif(p)
        embedding = (
            np.asarray(emb.embed_image(arr), dtype=np.float32)
            if (emb is not None and profile.taste_vector is not None)
            else None
        )
        item = {
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
        items.append(item)
        # Score this single photo now so the UI can show its provisional verdict
        # live. (Burst dedup + LLM arbitration below may still adjust a few.)
        r = score_features(
            items=[item],
            sharpness={iid: sh},
            blink={iid: bl},
            classifier=profile.classifier,
            taste_vector=profile.taste_vector,
            sharpness_floor=profile.thresholds.sharpness_floor,
            cfg=cfg,
        )[0]
        results.append(r)
        _emit({
            "phase": "photo", "index": i + 1, "total": total,
            "name": p.name, "band": r.decision, "score": r.score,
            "stars": _stars(r.score), "skipped": False,
            "reason": (r.reasons[0] if r.reasons else ""),
        })

    # --- Burst dedup + gray-zone arbitration --------------------------------- #
    _emit({"phase": "dedup"})
    results = dedup_bursts(
        results, hashes, profile.thresholds.burst_keep_rate, cfg
    )

    _emit({"phase": "arbitrate"})
    n_arbitrated = _arbitrate_maybe(
        results=results,
        judge=judge,
        profile_md=profile.profile_md,
        settings=settings,
        no_llm=no_llm,
        notes=notes,
    )

    # --- Export --------------------------------------------------------------- #
    _emit({"phase": "export"})
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
        n_arbitrated=n_arbitrated,
        results=results,
        report_path=report_path,
        sorted_dir=sorted_dir,
        notes=notes,
    )
