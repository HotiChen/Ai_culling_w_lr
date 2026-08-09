"""Tests for the pure-numpy pHash fallback.

Why this file exists: ``phash()`` prefers ``imagehash`` when installed and only
falls back to ``_fallback_phash`` otherwise. The existing ``test_phash.py`` only
exercises ``phash()``, so on any machine with ``imagehash`` present the fallback
is never executed — which is how a transposed DCT basis survived undetected.

The fallback's contract (see the module docstring) is to be a *substitute* for
``imagehash.phash``. If the two disagree, hashes computed on a machine with the
optional dep are not comparable to hashes computed on one without, and
``phash_hamming_max=8`` silently classifies every pair as "different".
So parity with imagehash is the property worth pinning down.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PIL")

from photovault.core.features.phash import (  # noqa: E402
    _fallback_phash,
    hamming,
)
from photovault.tests.make_images import blobs  # noqa: E402

_SEEDS = range(1, 21)


def _imagehash_reference(arr: np.ndarray) -> int:
    """The value ``imagehash.phash`` produces for *arr*, as an int."""
    imagehash = pytest.importorskip("imagehash")
    from PIL import Image

    return int(str(imagehash.phash(Image.fromarray(np.asarray(arr)), hash_size=8)), 16)


def test_fallback_matches_imagehash_exactly():
    """The fallback must be bit-identical to imagehash, not merely similar.

    Anything short of exact parity means a photo's hash depends on which
    optional packages happen to be installed.
    """
    mismatches = []
    for seed in _SEEDS:
        arr = blobs(seed=seed)
        got = _fallback_phash(arr)
        want = _imagehash_reference(arr)
        if got != want:
            mismatches.append((seed, hamming(got, want)))

    assert not mismatches, (
        f"{len(mismatches)}/{len(list(_SEEDS))} hashes differ from imagehash; "
        f"(seed, hamming) = {mismatches[:5]}"
    )


def test_fallback_dct_is_true_dct_ii():
    """The 2-D transform must equal scipy's DCT-II up to a positive scale factor.

    Guards the specific defect: a basis matrix built with the frequency and
    spatial indices swapped computes ``Dᵀ @ px @ D`` instead of ``D @ px @ Dᵀ``.
    Scale is irrelevant (the hash only thresholds against a median) but the
    matrix orientation is not.
    """
    scipy_fftpack = pytest.importorskip("scipy.fftpack")

    rng = np.random.RandomState(0)
    px = rng.rand(32, 32) * 255
    reference = scipy_fftpack.dct(scipy_fftpack.dct(px, axis=0), axis=1)

    from photovault.core.features.phash import _dct2

    got = _dct2(px)

    scale = reference[0, 0] / got[0, 0]
    assert scale > 0, "transform must not flip sign"
    assert np.allclose(got * scale, reference, atol=1e-6), (
        "2-D transform is not a scaled DCT-II — check the basis matrix orientation"
    )


def test_fallback_near_duplicates_stay_close():
    """A brightness-only change must not move the hash far."""
    a = blobs(seed=1)
    b = np.clip(a.astype(np.int16) + 6, 0, 255).astype(np.uint8)
    assert hamming(_fallback_phash(a), _fallback_phash(b)) <= 4


def test_fallback_different_images_stay_far():
    a = blobs(seed=1)
    b = blobs(seed=2)
    assert hamming(_fallback_phash(a), _fallback_phash(b)) > 8


def test_fallback_is_deterministic():
    a = blobs(seed=3)
    assert _fallback_phash(a) == _fallback_phash(a)


def test_fallback_returns_64_bit_value():
    value = _fallback_phash(blobs(seed=4))
    assert isinstance(value, int)
    assert 0 <= value < 2**64
