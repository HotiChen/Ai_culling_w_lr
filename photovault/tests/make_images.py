"""Synthesize tiny test images and a fake ``.lrprev`` for pixel-feature tests.

Mirrors :mod:`photovault.tests.make_fake` (catalog fixtures) but for the M2
pixel side. Pillow is the only hard dependency here; tests that need it use
``pytest.importorskip("PIL")``.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np


def checkerboard(size: int = 64, square: int = 4) -> np.ndarray:
    """High-frequency checkerboard (RGB uint8) — a maximally *sharp* image."""
    ys, xs = np.indices((size, size))
    board = (((xs // square) + (ys // square)) % 2) * 255
    return np.repeat(board[:, :, None].astype(np.uint8), 3, axis=2)


def solid(size: int = 64, value: int = 128) -> np.ndarray:
    """A flat gray image (RGB uint8) — minimal high-frequency content."""
    return np.full((size, size, 3), value, dtype=np.uint8)


def gradient(size: int = 64) -> np.ndarray:
    """A smooth horizontal gradient (RGB uint8)."""
    row = np.linspace(0, 255, size, dtype=np.uint8)
    img = np.tile(row, (size, 1))
    return np.repeat(img[:, :, None], 3, axis=2)


def blobs(seed: int = 0, size: int = 64) -> np.ndarray:
    """A photo-like image: low-res random blocks upsampled smoothly (RGB uint8).

    Unlike a checkerboard or gradient (which collapse under pHash's
    downscale+DCT), this has the kind of mid-frequency structure perceptual
    hashing is designed to distinguish.
    """
    from PIL import Image  # lazy

    rng = np.random.default_rng(seed)
    small = rng.integers(0, 256, (8, 8), dtype=np.uint8)
    big = np.asarray(Image.fromarray(small).resize((size, size), Image.BILINEAR))
    return np.repeat(big[:, :, None], 3, axis=2)


def jpeg_bytes(arr: np.ndarray, quality: int = 95) -> bytes:
    """Encode an RGB array to JPEG bytes via Pillow."""
    from PIL import Image  # lazy: Pillow only needed when actually encoding

    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def write_jpeg(path: str | Path, arr: np.ndarray, exif: dict | None = None) -> Path:
    """Write an RGB array to *path* as JPEG, optionally embedding EXIF."""
    from PIL import Image

    out = Path(path)
    img = Image.fromarray(arr)
    if exif:
        ex = img.getexif()
        for tag, value in exif.items():
            ex[tag] = value
        img.save(out, format="JPEG", exif=ex)
    else:
        img.save(out, format="JPEG")
    return out


def wrap_lrprev(jpeg: bytes, name_hint: str = "preview") -> bytes:
    """Wrap a JPEG inside a fake ``.lrprev`` container.

    Real Lightroom ``.lrprev`` files pack one or more JPEGs inside a Lua-ish
    wrapper with header/footer noise. We reproduce the shape that matters for
    the extractor: arbitrary leading/trailing bytes around the JPEG payload
    (delimited by SOI ``0xFFD8`` .. EOI ``0xFFD9``).
    """
    header = (
        b"AgLrPreview = {\n"
        b'\tname = "' + name_hint.encode() + b'",\n'
        b"\tlevels = {\n\t\t{\n\t\t\tdata = "
    )
    footer = b"\n\t\t},\n\t},\n}\n"
    # Throw in a tiny decoy byte run to make sure the carver does not trip on
    # stray 0xFF bytes outside a real JPEG.
    noise = b"\xff\x00\xff\x01"
    return header + noise + jpeg + footer


def write_lrprev(path: str | Path, arr: np.ndarray) -> Path:
    """Write a fake ``.lrprev`` wrapping a JPEG of *arr*; return the path."""
    out = Path(path)
    out.write_bytes(wrap_lrprev(jpeg_bytes(arr)))
    return out
