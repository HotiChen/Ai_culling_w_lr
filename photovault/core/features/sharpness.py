"""Sharpness via the variance of the Laplacian (opencv).

A focused image has strong high-frequency content, so its Laplacian has high
variance; a blurry image's Laplacian is flat. ``cv2`` is imported lazily.
"""

from __future__ import annotations

import numpy as np


def sharpness_score(image: np.ndarray) -> float:
    """Return the Laplacian variance of *image* (higher = sharper).

    Accepts an RGB ``(H, W, 3)`` or grayscale ``(H, W)`` uint8/float array.
    """
    import cv2  # lazy: opencv only needed when scoring pixels

    arr = np.asarray(image)
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(arr, cv2.CV_64F).var())
