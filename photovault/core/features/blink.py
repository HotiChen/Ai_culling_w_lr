"""Blink detection via the Eye Aspect Ratio (EAR).

The pure-math :func:`eye_aspect_ratio` is dependency-free and unit-tested
directly. Landmark detection sits behind the :class:`FaceLandmarker` Protocol so
tests can inject a fake; the real :class:`MediapipeLandmarker` imports mediapipe
lazily.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

# Below this EAR an eye is considered closed (standard ~0.2 threshold).
DEFAULT_EAR_THRESHOLD = 0.2

# Indices of mediapipe Face Mesh landmarks for the two eyes, ordered
# [corner, upper, upper, corner, lower, lower] to match EAR's p0..p5.
_LEFT_EYE_IDX = (33, 160, 158, 133, 153, 144)
_RIGHT_EYE_IDX = (362, 385, 387, 263, 373, 380)


def eye_aspect_ratio(points: np.ndarray) -> float:
    """Eye Aspect Ratio for 6 ordered eye landmarks ``[p0..p5]``.

    ``EAR = (||p1-p5|| + ||p2-p4||) / (2 * ||p0-p3||)``: high for an open eye,
    near zero when the lids meet.
    """
    p = np.asarray(points, dtype=np.float64)
    vertical = np.linalg.norm(p[1] - p[5]) + np.linalg.norm(p[2] - p[4])
    horizontal = np.linalg.norm(p[0] - p[3])
    if horizontal == 0:
        return 0.0
    return float(vertical / (2.0 * horizontal))


@runtime_checkable
class FaceLandmarker(Protocol):
    """Detects faces and returns per-face ``(left_eye, right_eye)`` point sets.

    Each eye is a ``(6, 2)`` array ordered for :func:`eye_aspect_ratio`. Returns
    an empty list when no face is found.
    """

    def eyes(self, image: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
        ...


def is_blinking(
    image: np.ndarray,
    landmarker: FaceLandmarker,
    threshold: float = DEFAULT_EAR_THRESHOLD,
) -> bool | None:
    """Whether any detected face has both eyes closed.

    Returns ``True``/``False`` per face decision, or ``None`` if no face was
    found (so callers can distinguish "no face" from "eyes open").
    """
    faces = landmarker.eyes(image)
    if not faces:
        return None
    for left, right in faces:
        ear = (eye_aspect_ratio(left) + eye_aspect_ratio(right)) / 2.0
        if ear < threshold:
            return True
    return False


class MediapipeLandmarker:
    """Real :class:`FaceLandmarker` backed by mediapipe Face Mesh (lazy import)."""

    def __init__(self, max_faces: int = 4) -> None:
        import mediapipe as mp  # lazy: heavy, optional dep

        self._mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=max_faces,
            refine_landmarks=True,
        )

    def eyes(self, image: np.ndarray) -> list[tuple[np.ndarray, np.ndarray]]:
        h, w = image.shape[:2]
        result = self._mesh.process(np.asarray(image))
        faces: list[tuple[np.ndarray, np.ndarray]] = []
        for face in result.multi_face_landmarks or []:
            lm = face.landmark

            def pts(idx: tuple[int, ...]) -> np.ndarray:
                return np.array([[lm[i].x * w, lm[i].y * h] for i in idx])

            faces.append((pts(_LEFT_EYE_IDX), pts(_RIGHT_EYE_IDX)))
        return faces
