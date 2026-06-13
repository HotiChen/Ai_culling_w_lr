"""The L3 ``taste_vector``: the average direction of your keeper embeddings.

Pure numpy — given a list of CLIP embeddings for the keepers, the taste vector
is their L2-normalized mean. At apply time, an image's cosine similarity to this
vector is one of the "taste" signals.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np


def compute_taste_vector(embeddings: Sequence[np.ndarray]) -> np.ndarray | None:
    """L2-normalized mean of keeper *embeddings*, or ``None`` if empty."""
    if len(embeddings) == 0:
        return None
    mat = np.asarray(embeddings, dtype=np.float32)
    mean = mat.mean(axis=0)
    norm = np.linalg.norm(mean)
    if norm == 0:
        return mean.astype(np.float32)
    return (mean / norm).astype(np.float32)


def similarity(vec: np.ndarray, taste_vector: np.ndarray) -> float:
    """Cosine similarity between *vec* and the *taste_vector* (in ``[-1, 1]``)."""
    a = np.asarray(vec, dtype=np.float32)
    b = np.asarray(taste_vector, dtype=np.float32)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
