"""Read EXIF from new photo files (stage B).

Returns the same :class:`~photovault.core.catalog.reader.ExifData` shape used by
the catalog reader, so the scoring pipeline can treat catalog images and fresh
files uniformly.

Two things that bite real photos and are handled here:

* aperture / ISO / focal length / shutter live in the **Exif sub-IFD**
  (``0x8769``), not the top-level IFD0 — we read both.
* RAW files (CR3/NEF/…) can't be opened by Pillow, so we pull EXIF from the
  embedded preview JPEG via ``rawpy`` (both imported lazily).
"""

from __future__ import annotations

import io
from pathlib import Path

from photovault.core.catalog.reader import ExifData

# RAW extensions worth trying rawpy on.
_RAW_EXTS = {".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf", ".rw2", ".orf"}

_EXIF_IFD = 0x8769  # ExifOffset — where FNumber/ISO/FocalLength/ExposureTime live


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        if isinstance(value, tuple) and len(value) == 2:
            return float(value[0]) / float(value[1]) if value[1] else None
        return float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _parse_pil_exif(img) -> ExifData:
    """Build :class:`ExifData` from a PIL image, reading the Exif sub-IFD."""
    from PIL.ExifTags import Base

    ex = img.getexif()
    if not ex:
        return ExifData()
    try:
        sub = ex.get_ifd(_EXIF_IFD) or {}
    except Exception:
        sub = {}

    def g(tag: int):
        # Prefer the Exif sub-IFD (where these tags really are), fall back to IFD0.
        return sub.get(tag, ex.get(tag))

    fnumber = _to_float(g(Base.FNumber.value))
    shutter = _to_float(g(Base.ExposureTime.value))
    iso = g(Base.ISOSpeedRatings.value)
    focal = _to_float(g(Base.FocalLength.value))
    flash = g(Base.Flash.value)

    iso_val = _to_float(iso)
    return ExifData(
        aperture_f=round(fnumber, 2) if fnumber is not None else None,
        shutter_seconds=shutter,
        iso=int(iso_val) if iso_val is not None else None,
        focal_length=focal,
        flash_fired=(bool(int(flash) & 1) if flash is not None else None),
    )


def _raw_preview_image(path: Path):
    """Open a RAW file's embedded preview JPEG as a PIL image (or None)."""
    try:
        import rawpy  # lazy, optional
        from PIL import Image  # lazy
    except ImportError:
        return None
    try:
        with rawpy.imread(str(path)) as raw:
            thumb = raw.extract_thumb()
        if thumb.format == rawpy.ThumbFormat.JPEG:
            return Image.open(io.BytesIO(thumb.data))
    except Exception:
        return None
    return None


def _read_exif_pillow(path: Path) -> ExifData:
    from PIL import Image  # lazy

    with Image.open(path) as img:
        return _parse_pil_exif(img)


def _read_exif_rawpy(path: Path) -> ExifData:
    """RAW files: read EXIF from the embedded preview JPEG."""
    img = _raw_preview_image(path)
    if img is None:
        return ExifData()
    try:
        return _parse_pil_exif(img)
    finally:
        try:
            img.close()
        except Exception:
            pass


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


def _capture_time_from_pil(img) -> str | None:
    from PIL.ExifTags import Base

    ex = img.getexif()
    if not ex:
        return None
    try:
        ifd = ex.get_ifd(_EXIF_IFD)
    except Exception:
        ifd = None
    value = ifd.get(Base.DateTimeOriginal.value) if ifd else None
    if value is None:
        value = ex.get(Base.DateTime.value)
    return str(value) if value else None


def read_capture_time(path: str | Path) -> str | None:
    """Read the capture-time string (EXIF ``DateTimeOriginal``) from *path*.

    Returns the raw EXIF text (``"YYYY:MM:DD HH:MM:SS"``) so it can be fed to
    :func:`photovault.core.catalog.cull_logic.parse_capture_time`. Works for RAW
    via the embedded preview. ``None`` when the tag is absent / unreadable.
    """
    p = Path(path)
    if not p.exists():
        return None
    if p.suffix.lower() in _RAW_EXTS:
        img = _raw_preview_image(p)
        if img is None:
            return None
        try:
            return _capture_time_from_pil(img)
        finally:
            try:
                img.close()
            except Exception:
                pass
    try:
        from PIL import Image  # lazy

        with Image.open(p) as img:
            return _capture_time_from_pil(img)
    except Exception:
        return None
