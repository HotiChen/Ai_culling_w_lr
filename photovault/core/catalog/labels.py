"""Export ``(features, label)`` rows for the metadata classifier.

This is the M1 training dataset: one row per image, metadata-only features
(pixels are added in M2) plus the keep/reject label derived in
:mod:`photovault.core.catalog.cull_logic`.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path

from photovault.core.catalog.cull_logic import (
    Label,
    group_bursts,
    label_for,
)
from photovault.core.catalog.reader import CatalogImage
from photovault.settings import CullSettings


@dataclass
class LabelRow:
    id_local: int
    filename: str
    aperture_f: float | None
    shutter_seconds: float | None
    iso: int | None
    focal_length: float | None
    flash_fired: bool | None
    burst_size: int
    burst_position: float | None  # 0=front .. 1=back; None for singletons
    rating: int | None
    pick: int
    label: str


FIELDNAMES = list(LabelRow.__annotations__.keys())


def build_rows(images: list[CatalogImage], cfg: CullSettings) -> list[LabelRow]:
    """Build one :class:`LabelRow` per image, including burst context."""
    # Map each image to its burst size and normalized position.
    burst_size: dict[int, int] = {}
    burst_pos: dict[int, float | None] = {}
    for burst in group_bursts(images, cfg):
        n = burst.size
        for idx, img in enumerate(burst.images):
            burst_size[img.id_local] = n
            burst_pos[img.id_local] = (idx / (n - 1)) if n > 1 else None

    rows: list[LabelRow] = []
    for img in images:
        rows.append(
            LabelRow(
                id_local=img.id_local,
                filename=img.filename,
                aperture_f=img.exif.aperture_f,
                shutter_seconds=(
                    round(img.exif.shutter_seconds, 6)
                    if img.exif.shutter_seconds is not None
                    else None
                ),
                iso=img.exif.iso,
                focal_length=img.exif.focal_length,
                flash_fired=img.exif.flash_fired,
                burst_size=burst_size.get(img.id_local, 1),
                burst_position=burst_pos.get(img.id_local),
                rating=img.rating,
                pick=img.pick,
                label=label_for(img, cfg).value,
            )
        )
    return rows


def write_csv(rows: list[LabelRow], path: str | Path) -> Path:
    """Write label rows to *path* (creating parent dirs). Returns the path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
    return out


def labeled_only(rows: list[LabelRow]) -> list[LabelRow]:
    """Drop UNLABELED rows — the trainable subset."""
    return [r for r in rows if r.label != Label.UNLABELED.value]
