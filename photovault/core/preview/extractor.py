"""Carve preview pixels out of Lightroom's preview cache.

``.lrprev`` files store JPEG payloads inside a Lua-ish text wrapper; we scan the
raw bytes for JPEG markers and keep the largest valid stream (Lightroom packs
several pyramid levels — the biggest is the highest resolution). Smart Preview
``.dng`` files are lossy DNGs decoded via ``rawpy`` (imported lazily so the
module imports cleanly without the heavy dep).
"""

from __future__ import annotations

from pathlib import Path

# JPEG framing markers.
_SOI = b"\xff\xd8"  # Start Of Image
_EOI = b"\xff\xd9"  # End Of Image


def carve_largest_jpeg(blob: bytes) -> bytes | None:
    """Return the largest embedded JPEG stream in *blob*, or ``None``.

    Scans for every SOI..EOI pair and keeps the longest one. Robust to stray
    ``0xFF`` bytes outside a real JPEG because it always anchors on a full
    SOI/EOI pair.
    """
    best: bytes | None = None
    start = blob.find(_SOI)
    while start != -1:
        end = blob.find(_EOI, start + 2)
        if end == -1:
            break
        candidate = blob[start : end + 2]
        if best is None or len(candidate) > len(best):
            best = candidate
        # Continue past this SOI to find any later (possibly larger) stream.
        start = blob.find(_SOI, start + 2)
    return best


def _extract_dng(path: Path) -> bytes | None:
    """Decode a Smart Preview ``.dng`` to JPEG bytes via lazy ``rawpy``."""
    try:
        import io

        import rawpy  # lazy: heavy, optional dep
        from PIL import Image  # lazy: only when actually decoding
    except ImportError:
        return None
    with rawpy.imread(str(path)) as raw:
        rgb = raw.postprocess()
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def extract_preview(path: str | Path) -> bytes | None:
    """Extract JPEG bytes from a preview file (``.lrprev`` or ``.dng``).

    Returns ``None`` if the file is missing or no preview can be carved.
    """
    p = Path(path)
    if not p.exists():
        return None
    if p.suffix.lower() == ".dng":
        return _extract_dng(p)
    return carve_largest_jpeg(p.read_bytes())


def find_preview(cache_root: str | Path, key: str) -> Path | None:
    """Locate a preview file for a catalog image under *cache_root*.

    Lightroom stores previews in a sharded tree keyed by the image's preview
    UUID (e.g. ``previews.lrdata/<X>/<key>/<key>-NNNN.lrprev``). We match any
    ``.lrprev`` / ``.dng`` whose basename starts with *key*; the largest match
    (highest pyramid level) wins.
    """
    root = Path(cache_root)
    if not root.exists():
        return None
    matches: list[Path] = []
    for pattern in (f"**/{key}*.lrprev", f"**/{key}*.dng"):
        matches.extend(p for p in root.glob(pattern) if p.is_file())
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_size)
