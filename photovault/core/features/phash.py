"""Perceptual hash (pHash) for near-duplicate / burst de-duplication.

Uses ``imagehash`` when available (lazy import) and otherwise falls back to a
pure-numpy DCT-based pHash so the module works with zero optional deps. Hashes
are plain ``int`` so callers can persist them and compare with :func:`hamming`.
"""

from __future__ import annotations

import numpy as np

_HASH_SIZE = 8  # 8x8 -> 64-bit hash


def _to_gray_float(image: np.ndarray) -> np.ndarray:
    arr = np.asarray(image).astype(np.float64)
    if arr.ndim == 3:
        arr = arr.mean(axis=2)
    return arr


def _fallback_phash(image: np.ndarray) -> int:
    """Pure-numpy DCT pHash (no third-party deps)."""
    from PIL import Image  # lazy: only used to resize consistently

    gray = _to_gray_float(image)
    img = Image.fromarray(gray.astype(np.uint8)).resize((32, 32), Image.BILINEAR)
    pixels = np.asarray(img, dtype=np.float64)

    # 2-D DCT-II via matrix multiply.
    n = 32
    k = np.arange(n)
    basis = np.cos(np.pi * (2 * k[:, None] + 1) * k[None, :] / (2 * n))
    dct = basis @ pixels @ basis.T

    low = dct[:_HASH_SIZE, :_HASH_SIZE]
    med = np.median(low[1:].flatten())  # drop DC term from the threshold
    bits = (low > med).flatten()

    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


def phash(image: np.ndarray) -> int:
    """Return a 64-bit perceptual hash of *image* as an ``int``."""
    try:
        import imagehash  # lazy, optional
        from PIL import Image
    except ImportError:
        return _fallback_phash(image)

    arr = np.asarray(image)
    pil = Image.fromarray(arr)
    return int(str(imagehash.phash(pil, hash_size=_HASH_SIZE)), 16)


def hamming(a: int, b: int) -> int:
    """Hamming distance between two integer hashes."""
    return bin(a ^ b).count("1")
