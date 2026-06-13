"""Global configuration via pydantic-settings.

All knobs are overridable through environment variables prefixed with
``PHOTOVAULT_`` or a ``.env`` file. Example::

    PHOTOVAULT_LLM__MODEL=gemma4:12b
    PHOTOVAULT_PROFILES_DIR=~/.photovault/profiles
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CullSettings(BaseModel):
    """Thresholds that turn Lightroom ratings/flags into keep/reject labels."""

    keep_rating: int = Field(
        3, ge=0, le=5, description="rating >= this counts as a keeper"
    )
    reject_rating: int = Field(
        1, ge=0, le=5, description="rating <= this (and not flagged pick) counts as a reject"
    )
    # Two frames shot within this gap belong to the same burst.
    burst_gap_seconds: float = Field(2.0, gt=0)
    # A burst must contain at least this many frames to be treated as a burst.
    burst_min_frames: int = Field(3, ge=2)


class StyleSettings(BaseModel):
    """How develop-setting clustering produces presets."""

    n_presets: int = Field(5, ge=1, description="number of representative looks (k)")
    kmeans_iters: int = Field(50, ge=1)
    random_seed: int = 42


class ScoreSettings(BaseModel):
    """Stage-B scoring knobs (M3): taste blend, decision bands, dedup.

    The taste score is a weighted mean of the classifier keep-probability and
    the cosine similarity to the taste_vector (remapped from ``[-1, 1]`` to
    ``[0, 1]``). Decisions fall into ``keep`` / ``maybe`` / ``reject`` bands:
    score ``>= keep_above`` keeps, ``< reject_below`` rejects, the gray zone in
    between is flagged ``maybe`` (M4 wires Gemma to arbitrate it).
    """

    # Blend weights for the taste score (normalized internally; need not sum 1).
    w_classifier: float = Field(0.6, ge=0.0, description="classifier keep-prob weight")
    w_taste: float = Field(0.4, ge=0.0, description="taste_vector similarity weight")
    # Decision bands over the final score in [0, 1].
    keep_above: float = Field(0.6, ge=0.0, le=1.0, description="score >= this -> keep")
    reject_below: float = Field(0.4, ge=0.0, le=1.0, description="score < this -> reject")
    # Burst de-duplication: two frames within this pHash hamming distance are
    # treated as near-duplicates of each other.
    phash_hamming_max: int = Field(
        8, ge=0, le=64, description="max pHash hamming distance for near-duplicates"
    )


class LLMSettings(BaseModel):
    """Local LLM (Ollama) used as the explainable arbiter.

    We use a single multimodal Gemma model for BOTH jobs:
      * stage A — write the human-readable taste rule-book (``profile.md``)
      * stage B — arbitrate only the gray-zone shots by actually looking at them

    Gemma 4 12B is multimodal (text + vision), so one model covers what the
    original design split across a text model and a separate vision model.
    On Apple Silicon, ``gemma4:12b-mlx`` is a faster MLX-backed variant.
    """

    enabled: bool = True
    host: str = "http://localhost:11434"
    # Single multimodal model for text + vision.
    model: str = "gemma4:12b"
    request_timeout_s: float = 120.0
    # Deterministic-ish output for reproducible rule-books / verdicts.
    temperature: float = 0.2


class Settings(BaseSettings):
    """Top-level application settings."""

    model_config = SettingsConfigDict(
        env_prefix="PHOTOVAULT_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
    )

    profiles_dir: Path = Field(
        default=Path.home() / ".photovault" / "profiles",
        description="where Taste Profiles are persisted",
    )

    cull: CullSettings = Field(default_factory=CullSettings)
    style: StyleSettings = Field(default_factory=StyleSettings)
    score: ScoreSettings = Field(default_factory=ScoreSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)

    def profile_dir(self, name: str) -> Path:
        """Absolute directory for a named profile."""
        return self.profiles_dir.expanduser() / name


def get_settings() -> Settings:
    """Construct settings (reads env / .env on each call)."""
    return Settings()
