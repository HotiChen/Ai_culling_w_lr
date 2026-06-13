"""Read EXIF from new photo files (stage B).

Returns the same :class:`~photovault.core.catalog.reader.ExifData` shape used by
the catalog reader, so the scoring pipeline can treat catalog images and fresh
files uniformly. JPEG/standard formats go through Pillow; RAW files fall back to
``rawpy`` (both imported lazily).
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

from photovault.core.catalog.reader import ExifData

# RAW extensions worth trying rawpy on.
_RAW_EXTS = {".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf", ".rw2", ".orf"}


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        # Pillow returns IFDRational / tuple / number.
        if isinstance(value, tuple) and len(value) == 2:
            return float(value[0]) / float(value[1]) if value[1] else None
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _read_exif_pillow(path: Path) -> ExifData:
    from PIL import Image  # lazy
    from PIL.ExifTags import Base

    with Image.open(path) as img:
        ex = img.getexif()
    if not ex:
        return ExifData()

    fnumber = _to_float(ex.get(Base.FNumber.value))
    shutter = _to_float(ex.get(Base.ExposureTime.value))
    iso = ex.get(Base.ISOSpeedRatings.value)
    focal = _to_float(ex.get(Base.FocalLength.value))
    flash = ex.get(Base.Flash.value)

    return ExifData(
        aperture_f=round(fnumber, 2) if fnumber is not None else None,
        shutter_seconds=shutter,
        iso=int(iso) if iso is not None else None,
        focal_length=focal,
        # EXIF Flash is a bitfield; bit 0 = fired.
        flash_fired=(bool(int(flash) & 1) if flash is not None else None),
    )


def _read_exif_rawpy(path: Path) -> ExifData:
    """RAW files: rawpy exposes only limited metadata, so best-effort."""
    try:
        import rawpy  # lazy, optional
    except ImportError:
        return ExifData()
    try:
        with rawpy.imread(str(path)):
            pass
    except Exception:
        return ExifData()
    # libraw does not surface aperture/shutter portably; defer to Pillow tags
    # when present (many RAWs carry an EXIF block Pillow can read).
    try:
        return _read_exif_pillow(path)
    except Exception:
        return ExifData()


def read_exif(path: str | Path) -> ExifData:
    """Read EXIF from *path*, returning an :class:`ExifData` (never raises)."""
    p = Path(path)
    if not p.exists():
        return ExifData()
    if p.suffix.lower() in _RAW_EXTS:
        return _read_exif_rawpy(p)
    try:
        return _read_exif_pillow(p)
    except Exception:
        return ExifData()


def read_capture_time(path: str | Path) -> str | None:
    """Read the capture-time string (EXIF ``DateTimeOriginal``) from *path*.

    Returns the raw EXIF text (``"YYYY:MM:DD HH:MM:SS"``) so it can be fed to
    :func:`photovault.core.catalog.cull_logic.parse_capture_time`, which already
    handles that format. Returns ``None`` when the tag is absent / unreadable.
    """
    p = Path(path)
    if not p.exists():
        return None
    try:
        from PIL import Image  # lazy
        from PIL.ExifTags import Base

        with Image.open(p) as img:
            ex = img.getexif()
        if not ex:
            return None
        # DateTimeOriginal lives in the Exif IFD; fall back to DateTime (0x0132).
        ifd = ex.get_ifd(0x8769)  # ExifOffset
        value = ifd.get(Base.DateTimeOriginal.value) if ifd else None
        if value is None:
            value = ex.get(Base.DateTime.value)
        return str(value) if value else None
    except Exception:
        return None
