from __future__ import annotations

import numpy as np

from photovault.core.features.blink import (
    FaceLandmarker,
    eye_aspect_ratio,
    is_blinking,
)

# A tiny 6-point eye in (x, y), ordered:
#   p0 = left corner, p3 = right corner (horizontal),
#   p1,p2 = upper lid, p5,p4 = lower lid (vertical pairs).
_OPEN_EYE = np.array(
    [
        [0.0, 0.0],   # p0 left corner
        [0.3, 0.4],   # p1 upper
        [0.7, 0.4],   # p2 upper
        [1.0, 0.0],   # p3 right corner
        [0.7, -0.4],  # p4 lower
        [0.3, -0.4],  # p5 lower
    ]
)
_CLOSED_EYE = _OPEN_EYE.copy()
_CLOSED_EYE[:, 1] *= 0.02  # collapse vertical extent -> lids touch


def test_open_eye_high_ear():
    assert eye_aspect_ratio(_OPEN_EYE) > 0.5


def test_closed_eye_near_zero_ear():
    assert eye_aspect_ratio(_CLOSED_EYE) < 0.05


class _FakeLandmarker(FaceLandmarker):
    """Returns one face with the supplied left/right eye points."""

    def __init__(self, left: np.ndarray, right: np.ndarray) -> None:
        self._left = left
        self._right = right

    def eyes(self, image):  # noqa: ANN001
        return [(self._left, self._right)]


def test_is_blinking_detects_closed_eyes():
    lm = _FakeLandmarker(_CLOSED_EYE, _CLOSED_EYE)
    assert is_blinking(np.zeros((8, 8, 3), np.uint8), landmarker=lm) is True


def test_is_blinking_open_eyes_not_blinking():
    lm = _FakeLandmarker(_OPEN_EYE, _OPEN_EYE)
    assert is_blinking(np.zeros((8, 8, 3), np.uint8), landmarker=lm) is False


def test_is_blinking_no_face_returns_none():
    class _NoFace(FaceLandmarker):
        def eyes(self, image):  # noqa: ANN001
            return []

    assert is_blinking(np.zeros((8, 8, 3), np.uint8), landmarker=_NoFace()) is None
