"""The keep/reject classifier (L2 metadata + L3 pixel features).

A thin, swappable wrapper around scikit-learn ``LogisticRegression`` (imported
lazily). The wrapper records the feature ordering so apply-time vectors line up
with training, handles the degenerate single-class case, and pickles cleanly
into the profile bundle.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

# Features the classifier consumes, in a fixed order. Pixel features (M2) plus
# the metadata features that mattered in M1.
FEATURE_NAMES = (
    "sharpness",
    "iso",
    "aperture_f",
    "focal_length",
    "shutter_seconds",
    "burst_position",
)

KEEP_LABEL = "keep"


@dataclass
class KeepRejectModel:
    """Pickle-friendly bundle: the sklearn estimator + its feature order.

    ``estimator`` is ``None`` for the single-class fallback, in which case
    :func:`predict_proba` returns the constant base rate.
    """

    feature_names: tuple[str, ...]
    estimator: object | None
    base_rate: float  # P(keep) when the estimator cannot discriminate


def _to_matrix(feats: Sequence[dict], names: tuple[str, ...]) -> np.ndarray:
    rows = []
    for f in feats:
        rows.append([_num(f.get(n)) for n in names])
    return np.asarray(rows, dtype=np.float64)


def _num(value: object) -> float:
    """Coerce to float; missing/None -> 0.0 (a neutral, learnable placeholder)."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def train_classifier(
    rows: Sequence[dict],
    features: Sequence[dict],
    feature_names: tuple[str, ...] = FEATURE_NAMES,
) -> KeepRejectModel:
    """Fit a keep/reject classifier from label *rows* + pixel/metadata *features*.

    *rows* and *features* are parallel: ``rows[i]["label"]`` is the target for
    ``features[i]``. Returns a :class:`KeepRejectModel` (always usable, even when
    only one class is present).
    """
    y = np.array([1 if r.get("label") == KEEP_LABEL else 0 for r in rows])
    base_rate = float(y.mean()) if len(y) else 0.0

    # Need both classes to fit a real boundary.
    if len(set(y.tolist())) < 2:
        return KeepRejectModel(feature_names, estimator=None, base_rate=base_rate)

    from sklearn.linear_model import LogisticRegression  # lazy
    from sklearn.preprocessing import StandardScaler  # lazy
    from sklearn.pipeline import Pipeline  # lazy

    X = _to_matrix(features, feature_names)
    estimator = Pipeline(
        [
            ("scale", StandardScaler()),
            ("clf", LogisticRegression(max_iter=1000)),
        ]
    )
    estimator.fit(X, y)
    return KeepRejectModel(feature_names, estimator=estimator, base_rate=base_rate)


def predict_proba(model: KeepRejectModel, feat: dict) -> float:
    """Probability that *feat* is a keeper, in ``[0, 1]``."""
    if model.estimator is None:
        return model.base_rate
    X = _to_matrix([feat], model.feature_names)
    proba = model.estimator.predict_proba(X)[0]
    # Column index of the positive ("keep" == 1) class.
    classes = list(model.estimator.classes_)
    pos = classes.index(1) if 1 in classes else -1
    return float(proba[pos])


def save_model(model: KeepRejectModel, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as fh:
        pickle.dump(model, fh)
    return out


def load_model(path: str | Path) -> KeepRejectModel:
    with Path(path).open("rb") as fh:
        return pickle.load(fh)
