"""The M1 learning pipeline: a folder of ``.lrcat`` files -> a Taste Profile.

This is the orchestration layer that ties together catalog reading (L1/L2),
style clustering, label export and profile persistence. Pixel-level L3
learning (taste_vector, classifier) is added in M2.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from photovault.core.catalog.cull_logic import Label, compute_stats, label_for
from photovault.core.catalog.labels import build_rows, write_csv
from photovault.core.catalog.reader import (
    CatalogImage,
    find_catalogs,
    iter_images,
    open_ro,
)
from photovault.core.catalog.style import extract_style
from photovault.core.judge import GemmaJudge, JudgeUnavailable
from photovault.core.profile.models import ProfileMeta, Thresholds
from photovault.core.profile.store import save_profile
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


def _read_all_images(catalogs: list[Path]) -> list[CatalogImage]:
    images: list[CatalogImage] = []
    for cat in catalogs:
        conn = open_ro(cat)
        try:
            images.extend(iter_images(conn))
        finally:
            conn.close()
    return images


def learn_from_folder(
    catalog_folder: str | Path,
    name: str,
    settings: Settings,
    use_llm: bool = True,
) -> LearnReport:
    """Run stage A and persist the profile. Returns a :class:`LearnReport`."""
    catalogs = find_catalogs(catalog_folder)
    if not catalogs:
        raise ValueError(f"no .lrcat files found under {catalog_folder}")

    images = _read_all_images(catalogs)
    if not images:
        raise ValueError("catalogs contain no images")

    # L2 stats + labels.
    stats = compute_stats(images, settings.cull)
    rows = build_rows(images, settings.cull)
    n_keepers = sum(1 for r in rows if r.label == Label.KEEP.value)
    n_rejects = sum(1 for r in rows if r.label == Label.REJECT.value)

    # L1 style presets.
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
        source_catalogs=[str(c) for c in catalogs],
        n_images=len(images),
        n_keepers=n_keepers,
        n_rejects=n_rejects,
        n_presets=len(style.presets),
    )

    # Optional LLM rule-book (Gemma). Falls back gracefully if unavailable.
    profile_md: str | None = None
    llm_used = False
    llm_note = ""
    if use_llm and settings.llm.enabled:
        try:
            judge = GemmaJudge(settings.llm)
            llm_stats = {**summary, "presets": [p.params for p in style.presets]}
            profile_md = judge.write_profile(name, llm_stats)
            llm_used = True
        except JudgeUnavailable as exc:
            llm_note = f"LLM unavailable, wrote placeholder profile.md ({exc})"
    else:
        llm_note = "LLM skipped (--no-llm or disabled)"

    # Write labels CSV to a temp file, then fold into the profile bundle.
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
        )

    return LearnReport(
        name=name,
        profile_dir=profile_dir,
        n_catalogs=len(catalogs),
        n_images=len(images),
        n_keepers=n_keepers,
        n_rejects=n_rejects,
        n_presets=len(style.presets),
        llm_used=llm_used,
        llm_note=llm_note,
    )
