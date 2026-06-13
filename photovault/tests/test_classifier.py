from __future__ import annotations

import pytest

pytest.importorskip("sklearn")

from photovault.core.learn.classifier import (  # noqa: E402
    FEATURE_NAMES,
    predict_proba,
    train_classifier,
)


def _synthetic():
    """Separable toy data: keepers are sharp & well-exposed, rejects aren't."""
    rows, feats = [], []
    for i in range(20):
        # Keepers: high sharpness, mid ISO.
        rows.append({"label": "keep"})
        feats.append({"sharpness": 800.0 + i, "iso": 200.0, "aperture_f": 2.0})
    for i in range(20):
        # Rejects: low sharpness, high ISO.
        rows.append({"label": "reject"})
        feats.append({"sharpness": 50.0 + i, "iso": 3200.0, "aperture_f": 8.0})
    return rows, feats


def test_train_returns_fitted_model():
    rows, feats = _synthetic()
    model = train_classifier(rows, feats)
    assert model is not None


def test_model_separates_obvious_cases():
    rows, feats = _synthetic()
    model = train_classifier(rows, feats)

    keep_like = {"sharpness": 900.0, "iso": 200.0, "aperture_f": 2.0}
    reject_like = {"sharpness": 40.0, "iso": 3200.0, "aperture_f": 8.0}

    p_keep = predict_proba(model, keep_like)
    p_reject = predict_proba(model, reject_like)
    assert p_keep > 0.5
    assert p_reject < 0.5
    assert p_keep > p_reject


def test_feature_names_stable():
    assert "sharpness" in FEATURE_NAMES


def test_single_class_falls_back():
    # All keepers -> cannot fit a real classifier; must not crash.
    rows = [{"label": "keep"}] * 5
    feats = [{"sharpness": 500.0}] * 5
    model = train_classifier(rows, feats)
    p = predict_proba(model, {"sharpness": 500.0})
    assert 0.0 <= p <= 1.0
