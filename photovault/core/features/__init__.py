"""Per-image pixel features (stage A + stage B).

Every heavy dependency (opencv, mediapipe, imagehash, rawpy, torch) is imported
lazily inside the function/class that needs it, so importing this package never
fails when an optional dep is absent.
"""

from photovault.core.features.blink import (
    FaceLandmarker,
    eye_aspect_ratio,
    is_blinking,
)
from photovault.core.features.clip_embed import Embedder
from photovault.core.features.exif import read_capture_time, read_exif
from photovault.core.features.phash import hamming, phash
from photovault.core.features.sharpness import sharpness_score

__all__ = [
    "Embedder",
    "FaceLandmarker",
    "eye_aspect_ratio",
    "hamming",
    "is_blinking",
    "phash",
    "read_capture_time",
    "read_exif",
    "sharpness_score",
]
