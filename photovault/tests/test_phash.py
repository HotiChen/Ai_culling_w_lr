from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("PIL")

from photovault.core.features.phash import hamming, phash  # noqa: E402
from photovault.tests.make_images import blobs  # noqa: E402


def _jitter(arr: np.ndarray) -> np.ndarray:
    """A near-duplicate: tiny brightness change, same structure."""
    return np.clip(arr.astype(np.int16) + 6, 0, 255).astype(np.uint8)


def test_near_duplicates_hash_close():
    a = blobs(seed=1)
    b = _jitter(a)
    assert hamming(phash(a), phash(b)) <= 4


def test_different_images_hash_far():
    a = blobs(seed=1)
    b = blobs(seed=2)
    assert hamming(phash(a), phash(b)) > 8


def test_identical_images_hash_equal():
    a = blobs(seed=3)
    assert hamming(phash(a), phash(a)) == 0
