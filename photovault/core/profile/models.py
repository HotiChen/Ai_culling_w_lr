"""Pydantic models describing the persisted Taste Profile."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ProfileMeta(BaseModel):
    """``meta.json`` — provenance and sample counts."""

    name: str
    version: str = "0.1.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source_catalogs: list[str] = Field(default_factory=list)
    n_images: int = 0
    n_keepers: int = 0
    n_rejects: int = 0
    n_presets: int = 0


class Thresholds(BaseModel):
    """``thresholds.json`` — L2 statistics + the learned culling knobs.

    In M1 these are the observed distributions; later milestones layer the
    learned L3 pixel thresholds (sharpness floor, blink rule) on top.
    """

    keep_rate: float = 0.0
    # Observed keeper EXIF distributions: {"min","median","max","mean"}.
    aperture_f: dict[str, float] = Field(default_factory=dict)
    iso: dict[str, float] = Field(default_factory=dict)
    focal_length: dict[str, float] = Field(default_factory=dict)
    # Burst behavior.
    burst_keep_rate: float = 0.0
    keep_position_mean: float = 0.0
    # Settings echoed back so apply-time matches learn-time logic.
    keep_rating: int = 3
    reject_rating: int = 1
    burst_gap_seconds: float = 2.0
    # Learned L3 pixel thresholds (M2). Optional so M1 profiles validate.
    sharpness_floor: float | None = None
