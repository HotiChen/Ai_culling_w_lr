"""M3: stage-B scoring engine — technical gate, taste blend, decision bands."""

from __future__ import annotations

import numpy as np
import pytest

from photovault.core.learn.classifier import KeepRejectModel
from photovault.core.score.engine import (
    ScoreResult,
    blend_score,
    decide,
    score_features,
)
from photovault.settings import ScoreSettings


# --------------------------------------------------------------------------- #
# Blend + band logic (pure, dependency-free)
# --------------------------------------------------------------------------- #
def test_blend_combines_classifier_and_similarity():
    cfg = ScoreSettings(w_classifier=0.5, w_taste=0.5)
    # keep_prob=1.0, similarity=1.0 -> sim01=1.0 -> blended 1.0.
    assert blend_score(1.0, 1.0, cfg) == pytest.approx(1.0)
    # keep_prob=0.0, similarity=-1.0 -> sim01=0.0 -> blended 0.0.
    assert blend_score(0.0, -1.0, cfg) == pytest.approx(0.0)
    # similarity remapped from [-1,1] to [0,1]: sim=0 -> 0.5.
    assert blend_score(1.0, 0.0, cfg) == pytest.approx(0.75)


def test_blend_drops_missing_terms():
    cfg = ScoreSettings(w_classifier=0.6, w_taste=0.4)
    # No similarity -> classifier alone.
    assert blend_score(0.8, None, cfg) == pytest.approx(0.8)
    # No classifier -> similarity alone (remapped).
    assert blend_score(None, 1.0, cfg) == pytest.approx(1.0)
    # Neither -> None (caller falls back to gate-only).
    assert blend_score(None, None, cfg) is None


def test_decide_bands():
    cfg = ScoreSettings(keep_above=0.6, reject_below=0.4)
    assert decide(0.9, cfg) == "keep"
    assert decide(0.6, cfg) == "keep"  # boundary is inclusive for keep
    assert decide(0.5, cfg) == "maybe"
    assert decide(0.4, cfg) == "maybe"  # reject is strict <
    assert decide(0.1, cfg) == "reject"


# --------------------------------------------------------------------------- #
# Technical gate
# --------------------------------------------------------------------------- #
def _const_model(p: float) -> KeepRejectModel:
    return KeepRejectModel(feature_names=(), estimator=None, base_rate=p)


def test_gate_rejects_blink():
    cfg = ScoreSettings()
    results = score_features(
        items=[{"id": "a", "path": "a.jpg", "burst_id": 0, "embedding": None}],
        sharpness={"a": 100.0},
        blink={"a": True},
        classifier=_const_model(0.9),
        taste_vector=None,
        sharpness_floor=None,
        cfg=cfg,
    )
    assert results[0].decision == "reject"
    assert any("blink" in r.lower() for r in results[0].reasons)


def test_gate_rejects_soft_focus_below_floor():
    cfg = ScoreSettings()
    results = score_features(
        items=[{"id": "a", "path": "a.jpg", "burst_id": 0, "embedding": None}],
        sharpness={"a": 5.0},
        blink={"a": None},
        classifier=_const_model(0.9),
        taste_vector=None,
        sharpness_floor=50.0,
        cfg=cfg,
    )
    assert results[0].decision == "reject"
    assert any("sharp" in r.lower() or "focus" in r.lower() for r in results[0].reasons)


def test_no_floor_means_no_sharpness_gate():
    cfg = ScoreSettings(keep_above=0.6, reject_below=0.4)
    results = score_features(
        items=[{"id": "a", "path": "a.jpg", "burst_id": 0, "embedding": None}],
        sharpness={"a": 0.1},
        blink={"a": None},
        classifier=_const_model(0.9),
        taste_vector=None,
        sharpness_floor=None,
        cfg=cfg,
    )
    assert results[0].decision == "keep"


def test_score_result_shape_and_taste_term():
    cfg = ScoreSettings(w_classifier=0.5, w_taste=0.5, keep_above=0.6, reject_below=0.4)
    tv = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    emb = np.array([1.0, 0.0, 0.0], dtype=np.float32)  # identical -> sim 1.0
    results = score_features(
        items=[{"id": "a", "path": "a.jpg", "burst_id": 3, "embedding": emb}],
        sharpness={"a": 100.0},
        blink={"a": False},
        classifier=_const_model(1.0),
        taste_vector=tv,
        sharpness_floor=10.0,
        cfg=cfg,
    )
    r = results[0]
    assert isinstance(r, ScoreResult)
    assert r.id == "a"
    assert r.burst_id == 3
    assert r.score == pytest.approx(1.0)
    assert r.decision == "keep"


def test_gate_only_when_no_models():
    """M1-only profile (no classifier, no taste_vector): gate-only, flagged maybe."""
    cfg = ScoreSettings()
    results = score_features(
        items=[{"id": "a", "path": "a.jpg", "burst_id": 0, "embedding": None}],
        sharpness={"a": 100.0},
        blink={"a": None},
        classifier=None,
        taste_vector=None,
        sharpness_floor=None,
        cfg=cfg,
    )
    r = results[0]
    assert r.score is None
    # Passes the gate but cannot be scored -> not a confident keep/reject.
    assert r.decision == "maybe"
