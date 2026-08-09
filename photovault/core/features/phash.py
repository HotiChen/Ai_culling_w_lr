"""Perceptual hash (pHash) for near-duplicate / burst de-duplication.

Uses ``imagehash`` when available (lazy import) and otherwise falls back to a
pure-numpy DCT-based pHash so the module works with zero optional deps. Hashes
are plain ``int`` so callers can persist them and compare with :func:`hamming`.
"""

from __future__ import annotations

import numpy as np

_HASH_SIZE = 8  # 8x8 -> 64-bit hash
_DCT_SIZE = _HASH_SIZE * 4  # imagehash's highfreq_factor of 4 -> 32x32 transform


def _to_gray(image: np.ndarray) -> "Image.Image":
    """Grayscale *image* the same way ``imagehash`` does.

    Uses PIL's ``convert("L")`` (ITU-R 601-2 luma) rather than a flat channel
    mean, because the fallback has to reproduce ``imagehash`` bit-for-bit.
    """
    from PIL import Image  # lazy: keeps the module importable without Pillow

    arr = np.asarray(image)
    if arr.dtype != np.uint8:
        arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr).convert("L")


def _dct2(pixels: np.ndarray) -> np.ndarray:
    """2-D DCT-II via matrix multiply, equal to ``scipy.fftpack`` up to scale.

    The basis is ``D[k, j] = cos(pi * k * (2j + 1) / 2N)`` — frequency indexes
    the rows, space indexes the columns. Building it the other way round yields
    ``Dᵀ`` and silently computes ``Dᵀ @ px @ D``, which is a different transform
    (not merely a transposed one) and shifts roughly a third of the hash bits.

    The constant factor of 2 in scipy's definition is omitted deliberately: the
    hash only compares coefficients against their own median, so any positive
    scaling cancels out.
    """
    n = pixels.shape[0]
    k = np.arange(n)
    basis = np.cos(np.pi * k[:, None] * (2 * k[None, :] + 1) / (2 * n))
    return basis @ pixels @ basis.T


def _fallback_phash(image: np.ndarray) -> int:
    """Pure-numpy DCT pHash (no third-party deps).

    Reproduces ``imagehash.phash(..., hash_size=8)`` exactly. That parity is the
    point: hashes are persisted and compared against ``phash_hamming_max``, so a
    fallback that merely approximated imagehash would make results depend on
    whether an optional package happened to be installed.
    """
    from PIL import Image  # lazy: only used to resize consistently

    img = _to_gray(image).resize((_DCT_SIZE, _DCT_SIZE), Image.LANCZOS)
    pixels = np.asarray(img, dtype=np.float64)

    low = _dct2(pixels)[:_HASH_SIZE, :_HASH_SIZE]
    # Median over all 64 low-frequency coefficients, DC included — this is what
    # imagehash does, and the median is robust enough that the lone DC outlier
    # does not drag the threshold.
    med = np.median(low)
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
