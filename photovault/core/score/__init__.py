"""Stage-B scoring: technical gate + taste blend + burst dedup (M3)."""

from photovault.core.score.dedup import dedup_bursts, keep_k
from photovault.core.score.engine import (
    KEEP,
    MAYBE,
    REJECT,
    ScoreResult,
    blend_score,
    decide,
    score_features,
)
from photovault.core.score.pipeline import ApplyReport, apply_to_folder

__all__ = [
    "KEEP",
    "MAYBE",
    "REJECT",
    "ApplyReport",
    "ScoreResult",
    "apply_to_folder",
    "blend_score",
    "decide",
    "dedup_bursts",
    "keep_k",
    "score_features",
]
