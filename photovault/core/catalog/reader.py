"""Read-only access to a Lightroom Classic catalog.

The catalog is a SQLite database. We open it ``immutable=1`` so we can never
mutate the user's catalog and so it works even while Lightroom holds a lock.

The schema is introspected defensively: column names have drifted across
Lightroom versions, so :func:`iter_images` only selects columns that actually
exist and degrades gracefully when an optional table (e.g. develop settings)
is missing.
"""

from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


# --------------------------------------------------------------------------- #
# Connection helpers
# --------------------------------------------------------------------------- #
def open_ro(catalog_path: str | Path) -> sqlite3.Connection:
    """Open a catalog strictly read-only and immutable.

    Raises ``FileNotFoundError`` if the path does not exist so callers get a
    clear error rather than SQLite silently creating an empty database.
    """
    path = Path(catalog_path)
    if not path.exists():
        raise FileNotFoundError(f"catalog not found: {path}")
    uri = f"file:{path}?mode=ro&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def find_catalogs(folder: str | Path) -> list[Path]:
    """Recursively find ``.lrcat`` files under *folder*, sorted by path."""
    root = Path(folder)
    if not root.exists():
        raise FileNotFoundError(f"folder not found: {root}")
    return sorted(p for p in root.rglob("*.lrcat") if p.is_file())


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """Return column names of *table* (empty list if it does not exist)."""
    if not table_exists(conn, table):
        return []
    return [r["name"] for r in conn.execute(f'PRAGMA table_info("{table}")')]


# --------------------------------------------------------------------------- #
# APEX / unit conversions (Lightroom stores EXIF in APEX units)
# --------------------------------------------------------------------------- #
def apex_to_fnumber(aperture: float | None) -> float | None:
    """APEX aperture value (Av) -> f-number. f = 2^(Av/2)."""
    if aperture is None:
        return None
    return round(2.0 ** (aperture / 2.0), 2)


def apex_to_shutter_seconds(shutter: float | None) -> float | None:
    """APEX shutter value (Tv) -> exposure time in seconds. t = 2^(-Tv)."""
    if shutter is None:
        return None
    return 2.0 ** (-shutter)


# --------------------------------------------------------------------------- #
# Data records
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ExifData:
    aperture_f: float | None = None          # f-number (converted from APEX)
    shutter_seconds: float | None = None     # seconds (converted from APEX)
    iso: int | None = None
    focal_length: float | None = None        # mm
    flash_fired: bool | None = None


@dataclass(frozen=True)
class DevelopSettings:
    """Parsed develop adjustments. ``params`` holds numeric crs-style keys."""

    has_adjustments: bool = False
    params: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class CatalogImage:
    id_local: int
    base_name: str
    extension: str
    file_format: str | None
    capture_time: str | None          # ISO-ish text as stored by Lightroom
    rating: int | None                # 0..5
    pick: int                         # 1 = flagged, -1 = rejected, 0 = none
    color_label: str | None
    width: int | None
    height: int | None
    exif: ExifData
    develop: DevelopSettings

    @property
    def filename(self) -> str:
        return f"{self.base_name}.{self.extension}" if self.extension else self.base_name


# --------------------------------------------------------------------------- #
# Develop-settings text parsing
# --------------------------------------------------------------------------- #
# Lightroom serializes develop settings as a Lua-ish table of ``key = value``
# pairs. We tolerantly pull out every numeric scalar; non-numeric values
# (strings, nested tables, booleans) are ignored for the M1 feature vector.
_KV_NUMERIC = re.compile(
    r'([A-Za-z][A-Za-z0-9_]*)\s*=\s*(-?\d+(?:\.\d+)?)'
)


def parse_develop_text(text: str | None) -> dict[str, float]:
    if not text:
        return {}
    out: dict[str, float] = {}
    for key, val in _KV_NUMERIC.findall(text):
        try:
            num = float(val)
        except ValueError:
            continue
        if math.isfinite(num):
            out[key] = num
    return out


# --------------------------------------------------------------------------- #
# Image iteration
# --------------------------------------------------------------------------- #
def _coerce_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def iter_images(conn: sqlite3.Connection) -> Iterator[CatalogImage]:
    """Yield every image in the catalog, joined with EXIF + develop settings.

    Works against the standard Lightroom Classic schema and is tolerant of
    missing optional tables/columns.
    """
    img_cols = table_columns(conn, "Adobe_images")
    if not img_cols:
        raise ValueError("not a Lightroom catalog: missing Adobe_images table")

    has_file = table_exists(conn, "AgLibraryFile")
    has_exif = table_exists(conn, "AgHarvestedExifMetadata")
    has_dev = table_exists(conn, "Adobe_imageDevelopSettings")
    exif_cols = table_columns(conn, "AgHarvestedExifMetadata")
    dev_cols = table_columns(conn, "Adobe_imageDevelopSettings")

    def col(table_alias: str, name: str, available: list[str], default: str = "NULL") -> str:
        return f"{table_alias}.{name}" if name in available else default

    select = [
        "i.id_local AS id_local",
        col("i", "captureTime", img_cols) + " AS capture_time",
        col("i", "rating", img_cols) + " AS rating",
        col("i", "pick", img_cols) + " AS pick",
        col("i", "colorLabels", img_cols) + " AS color_label",
        col("i", "fileFormat", img_cols) + " AS file_format",
        col("i", "fileWidth", img_cols) + " AS width",
        col("i", "fileHeight", img_cols) + " AS height",
    ]
    joins = ["FROM Adobe_images i"]

    if has_file:
        select += [
            col("f", "baseName", table_columns(conn, "AgLibraryFile")) + " AS base_name",
            col("f", "extension", table_columns(conn, "AgLibraryFile")) + " AS extension",
        ]
        joins.append("LEFT JOIN AgLibraryFile f ON f.id_local = i.rootFile")
    else:
        select += ["NULL AS base_name", "NULL AS extension"]

    if has_exif:
        select += [
            col("e", "aperture", exif_cols) + " AS aperture",
            col("e", "shutterSpeed", exif_cols) + " AS shutter",
            col("e", "isoSpeedRating", exif_cols) + " AS iso",
            col("e", "focalLength", exif_cols) + " AS focal_length",
            col("e", "flashFired", exif_cols) + " AS flash_fired",
        ]
        joins.append("LEFT JOIN AgHarvestedExifMetadata e ON e.image = i.id_local")
    else:
        select += [
            "NULL AS aperture", "NULL AS shutter", "NULL AS iso",
            "NULL AS focal_length", "NULL AS flash_fired",
        ]

    if has_dev:
        select += [
            col("d", "text", dev_cols) + " AS develop_text",
            col("d", "hasDevelopAdjustments", dev_cols) + " AS has_dev",
        ]
        joins.append("LEFT JOIN Adobe_imageDevelopSettings d ON d.image = i.id_local")
    else:
        select += ["NULL AS develop_text", "NULL AS has_dev"]

    sql = "SELECT " + ", ".join(select) + " " + " ".join(joins) + " ORDER BY i.id_local"

    for r in conn.execute(sql):
        exif = ExifData(
            aperture_f=apex_to_fnumber(r["aperture"]),
            shutter_seconds=apex_to_shutter_seconds(r["shutter"]),
            iso=_coerce_int(r["iso"]),
            focal_length=(float(r["focal_length"]) if r["focal_length"] is not None else None),
            flash_fired=(bool(r["flash_fired"]) if r["flash_fired"] is not None else None),
        )
        params = parse_develop_text(r["develop_text"])
        has_dev_flag = bool(r["has_dev"]) if r["has_dev"] is not None else bool(params)
        develop = DevelopSettings(has_adjustments=has_dev_flag, params=params)

        yield CatalogImage(
            id_local=int(r["id_local"]),
            base_name=r["base_name"] or f"img{r['id_local']}",
            extension=(r["extension"] or "").lower(),
            file_format=r["file_format"],
            capture_time=r["capture_time"],
            rating=_coerce_int(r["rating"]),
            pick=_coerce_int(r["pick"]) or 0,
            color_label=r["color_label"] or None,
            width=_coerce_int(r["width"]),
            height=_coerce_int(r["height"]),
            exif=exif,
            develop=develop,
        )
