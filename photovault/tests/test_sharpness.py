from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("cv2")

from photovault.core.features.sharpness import sharpness_score  # noqa: E402
from photovault.tests.make_images import checkerboard, solid  # noqa: E402


def _blur(arr: np.ndarray) -> np.ndarray:
    import cv2

    return cv2.GaussianBlur(arr, (9, 9), 4.0)


def test_sharp_beats_blurry():
    sharp = checkerboard(64, 4)
    blurry = _blur(sharp)
    assert sharpness_score(sharp) > sharpness_score(blurry)


def test_flat_image_is_near_zero():
    assert sharpness_score(solid(64, 128)) < 1.0


def test_accepts_grayscale():
    # A 2-D array should not raise and should give a finite, positive score.
    gray = checkerboard(64, 4)[:, :, 0]
    score = sharpness_score(gray)
    assert score > 0
