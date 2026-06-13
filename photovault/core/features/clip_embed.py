"""CLIP image/text embeddings behind a swappable :class:`Embedder` Protocol.

Tests inject a deterministic fake; the real :class:`OpenClipEmbedder` uses
open-clip-torch on the best available torch device (MPS on Apple Silicon, else
CPU) and imports everything lazily so this module never pulls torch at import.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np


def device() -> str:
    """Pick the best torch device: ``mps`` (Apple Silicon) > ``cuda`` > ``cpu``.

    Returns ``"cpu"`` if torch is not installed, so callers can probe cheaply.
    """
    try:
        import torch  # lazy
    except ImportError:
        return "cpu"
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


@runtime_checkable
class Embedder(Protocol):
    """Maps images and text into a shared, L2-normalized embedding space."""

    def embed_image(self, arr: np.ndarray) -> np.ndarray:
        ...

    def embed_text(self, text: str) -> np.ndarray:
        ...


class OpenClipEmbedder:
    """Real :class:`Embedder` using open-clip-torch (lazy torch import).

    The model is loaded on first use; construction merely records the choice so
    importing/instantiating without torch fails loudly only when actually used.
    """

    def __init__(
        self,
        model_name: str = "ViT-B-32",
        pretrained: str = "laion2b_s34b_b79k",
        device_str: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.pretrained = pretrained
        self.device = device_str or device()
        self._model = None
        self._preprocess = None
        self._tokenizer = None

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        import open_clip  # lazy: heavy, optional dep
        import torch  # noqa: F401

        model, _, preprocess = open_clip.create_model_and_transforms(
            self.model_name, pretrained=self.pretrained, device=self.device
        )
        model.eval()
        self._model = model
        self._preprocess = preprocess
        self._tokenizer = open_clip.get_tokenizer(self.model_name)

    def embed_image(self, arr: np.ndarray) -> np.ndarray:
        import torch
        from PIL import Image

        self._ensure_loaded()
        pil = Image.fromarray(np.asarray(arr))
        tensor = self._preprocess(pil).unsqueeze(0).to(self.device)
        with torch.no_grad():
            feats = self._model.encode_image(tensor)
            feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats.cpu().numpy()[0].astype(np.float32)

    def embed_text(self, text: str) -> np.ndarray:
        import torch

        self._ensure_loaded()
        tokens = self._tokenizer([text]).to(self.device)
        with torch.no_grad():
            feats = self._model.encode_text(tokens)
            feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats.cpu().numpy()[0].astype(np.float32)
