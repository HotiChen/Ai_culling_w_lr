from __future__ import annotations

import numpy as np
import pytest

from photovault.core.features.clip_embed import Embedder, device


class FakeEmbedder(Embedder):
    """Deterministic embeddings — never downloads a model.

    Hashes the input to a fixed-dim vector so the same input always maps to the
    same direction; image and text spaces are independent but reproducible.
    """

    dim = 8

    def _vec(self, seed: int) -> np.ndarray:
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(self.dim).astype(np.float32)
        return v / np.linalg.norm(v)

    def embed_image(self, arr: np.ndarray) -> np.ndarray:
        return self._vec(int(arr.sum()) % (2**31))

    def embed_text(self, text: str) -> np.ndarray:
        return self._vec(abs(hash(text)) % (2**31))


def test_fake_embedder_is_deterministic():
    e = FakeEmbedder()
    a = np.ones((4, 4, 3), np.uint8)
    assert np.allclose(e.embed_image(a), e.embed_image(a))
    assert np.allclose(e.embed_text("cat"), e.embed_text("cat"))


def test_fake_embedder_distinguishes_inputs():
    e = FakeEmbedder()
    a = np.zeros((4, 4, 3), np.uint8)
    b = np.full((4, 4, 3), 200, np.uint8)
    assert not np.allclose(e.embed_image(a), e.embed_image(b))


def test_embeddings_are_unit_norm():
    e = FakeEmbedder()
    v = e.embed_image(np.ones((4, 4, 3), np.uint8))
    assert np.linalg.norm(v) == pytest.approx(1.0)


def test_device_returns_str():
    assert device() in {"mps", "cpu", "cuda"}
