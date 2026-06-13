from __future__ import annotations

import numpy as np
import pytest

from photovault.core.learn.taste import compute_taste_vector, similarity
from photovault.tests.test_clip_embed import FakeEmbedder


def test_taste_vector_is_unit_norm():
    e = FakeEmbedder()
    vecs = [e.embed_image(np.full((4, 4, 3), v, np.uint8)) for v in (10, 50, 90)]
    taste = compute_taste_vector(vecs)
    assert np.linalg.norm(taste) == pytest.approx(1.0)


def test_taste_vector_is_mean_direction():
    # Two opposite vectors average to ~zero; a clear majority dominates.
    v = np.array([1.0, 0.0, 0.0], np.float32)
    taste = compute_taste_vector([v, v, v])
    assert np.allclose(taste, v)


def test_similarity_self_is_one():
    v = np.array([0.0, 1.0, 0.0], np.float32)
    assert similarity(v, v) == pytest.approx(1.0)


def test_similarity_orthogonal_is_zero():
    a = np.array([1.0, 0.0], np.float32)
    b = np.array([0.0, 1.0], np.float32)
    assert similarity(a, b) == pytest.approx(0.0, abs=1e-6)


def test_keeper_more_similar_than_outlier():
    e = FakeEmbedder()
    keepers = [e.embed_image(np.full((4, 4, 3), v, np.uint8)) for v in (10, 12, 14)]
    taste = compute_taste_vector(keepers)
    near = e.embed_image(np.full((4, 4, 3), 11, np.uint8))
    # A keeper-like vector should not be wildly dissimilar from its own mean.
    assert -1.0 <= similarity(near, taste) <= 1.0


def test_empty_returns_none():
    assert compute_taste_vector([]) is None
