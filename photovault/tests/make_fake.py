"""Build a synthetic Lightroom Classic ``.lrcat`` for golden-file testing.

The schema mirrors the real catalog tables that :mod:`photovault.core.catalog`
reads, with EXIF stored in APEX units (as Lightroom does). Keeping this in one
place lets every test share one realistic fixture.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


def _av(fnumber: float) -> float:
    """f-number -> APEX aperture value."""
    return 2.0 * math.log2(fnumber)


def _tv(seconds: float) -> float:
    """exposure seconds -> APEX shutter value."""
    return -math.log2(seconds)


@dataclass
class FakeImage:
    base_name: str
    capture_time: str
    rating: int | None = None
    pick: int = 0
    fnumber: float = 2.8
    shutter_s: float = 1 / 250
    iso: int = 200
    focal: float = 50.0
    flash: bool = False
    develop: dict[str, float] = field(default_factory=dict)
    extension: str = "dng"
    fmt: str = "RAW"


def _develop_text(params: dict[str, float]) -> str:
    """Serialize params in Lightroom's Lua-ish develop-settings format."""
    body = ",\n".join(f"\t{k} = {v}" for k, v in params.items())
    return "s = {\n" + body + ",\n}\n"


def write_catalog(path: str | Path, images: list[FakeImage]) -> Path:
    """Create a synthetic catalog at *path* and return it."""
    out = Path(path)
    if out.exists():
        out.unlink()
    conn = sqlite3.connect(out)
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE AgLibraryRootFolder (
            id_local INTEGER PRIMARY KEY, absolutePath TEXT, name TEXT);
        CREATE TABLE AgLibraryFolder (
            id_local INTEGER PRIMARY KEY, pathFromRoot TEXT, rootFolder INTEGER);
        CREATE TABLE AgLibraryFile (
            id_local INTEGER PRIMARY KEY, baseName TEXT, extension TEXT,
            idx_filename TEXT, folder INTEGER, originalFilename TEXT);
        CREATE TABLE Adobe_images (
            id_local INTEGER PRIMARY KEY, rootFile INTEGER, captureTime TEXT,
            rating REAL, pick REAL, colorLabels TEXT, fileFormat TEXT,
            fileWidth INTEGER, fileHeight INTEGER, orientation TEXT);
        CREATE TABLE AgHarvestedExifMetadata (
            id_local INTEGER PRIMARY KEY, image INTEGER, aperture REAL,
            shutterSpeed REAL, isoSpeedRating INTEGER, focalLength REAL,
            flashFired INTEGER);
        CREATE TABLE Adobe_imageDevelopSettings (
            id_local INTEGER PRIMARY KEY, image INTEGER, text TEXT,
            hasDevelopAdjustments INTEGER, digest TEXT);
        """
    )

    cur.execute(
        "INSERT INTO AgLibraryRootFolder VALUES (1, '/Photos/', 'Photos')"
    )
    cur.execute(
        "INSERT INTO AgLibraryFolder VALUES (1, 'shoot/', 1)"
    )

    for i, im in enumerate(images, start=1):
        cur.execute(
            "INSERT INTO AgLibraryFile VALUES (?,?,?,?,?,?)",
            (i, im.base_name, im.extension, f"{im.base_name}.{im.extension}", 1,
             f"{im.base_name}.{im.extension}"),
        )
        cur.execute(
            "INSERT INTO Adobe_images VALUES (?,?,?,?,?,?,?,?,?,?)",
            (i, i, im.capture_time, im.rating, float(im.pick), None, im.fmt,
             6000, 4000, "AB"),
        )
        cur.execute(
            "INSERT INTO AgHarvestedExifMetadata VALUES (?,?,?,?,?,?,?)",
            (i, i, _av(im.fnumber), _tv(im.shutter_s), im.iso, im.focal,
             1 if im.flash else 0),
        )
        has_dev = 1 if im.develop else 0
        cur.execute(
            "INSERT INTO Adobe_imageDevelopSettings VALUES (?,?,?,?,?)",
            (i, i, _develop_text(im.develop) if im.develop else None, has_dev, None),
        )

    conn.commit()
    conn.close()
    return out


def default_images() -> list[FakeImage]:
    """A representative shoot: one burst + singles, with looks and labels.

    - A 5-frame burst at f/2.0; the photographer keeps the LAST two frames
      (back-of-burst preference) and rejects the early ones.
    - Two warm, edited keeper portraits at f/1.4.
    - Two cool, contrasty edited keepers at f/4.
    - One unedited, unrated single (UNLABELED).
    - One blinked reject.
    """
    warm = {"Exposure2012": 0.35, "Temperature": 5600, "Tint": 12,
            "Highlights2012": -40, "Shadows2012": 30, "Vibrance": 15,
            "Contrast2012": 8}
    cool = {"Exposure2012": -0.1, "Temperature": 4800, "Tint": -5,
            "Highlights2012": -10, "Shadows2012": 10, "Contrast2012": 35,
            "Clarity2012": 20}

    imgs: list[FakeImage] = []
    # Burst: 5 frames ~0.5s apart, keep last two.
    for k in range(5):
        sec = 20 + k  # seconds within the same minute, < burst gap apart
        rating = 4 if k >= 3 else 1
        pick = 1 if k >= 3 else -1
        imgs.append(FakeImage(
            base_name=f"burst_{k}",
            capture_time=f"2023-05-01T14:30:{sec:02d}",
            rating=rating, pick=pick, fnumber=2.0, iso=400, focal=85.0,
            develop=warm if k >= 3 else {},
        ))

    # Warm keeper portraits (far apart in time -> singletons).
    imgs.append(FakeImage("portrait_a", "2023-05-01T15:00:00", rating=5, pick=1,
                          fnumber=1.4, iso=200, focal=85.0, develop=warm))
    imgs.append(FakeImage("portrait_b", "2023-05-01T15:10:00", rating=4, pick=1,
                          fnumber=1.4, iso=320, focal=85.0, develop=warm))

    # Cool contrasty keepers.
    imgs.append(FakeImage("scape_a", "2023-05-01T16:00:00", rating=4,
                          fnumber=4.0, iso=100, focal=24.0, develop=cool))
    imgs.append(FakeImage("scape_b", "2023-05-01T16:20:00", rating=5,
                          fnumber=4.0, iso=100, focal=35.0, develop=cool))

    # Unlabeled single (no rating, no flag, no edits).
    imgs.append(FakeImage("misc_single", "2023-05-01T17:00:00", rating=None,
                          fnumber=2.8, iso=800, focal=50.0))

    # Explicit reject.
    imgs.append(FakeImage("blink_reject", "2023-05-01T18:00:00", rating=0,
                          pick=-1, fnumber=2.8, iso=1600, focal=50.0))

    return imgs
