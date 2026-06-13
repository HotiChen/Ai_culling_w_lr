"""Stage-B scoring engine (M3): technical gate + taste blend + decision bands.

Pure scoring logic. Pixel features (sharpness, blink) are passed in as plain
dicts keyed by image id so the engine never imports opencv/mediapipe — the
caller (``pipeline``) injects them, and tests inject fakes. The classifier and
taste_vector come from the loaded profile and are both optional, so an M1-only
profile degrades to a technical-gate-only pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from photovault.core.learn.classifier import KeepRejectModel, predict_proba
from photovault.core.learn.taste import similarity
from photovault.settings import ScoreSettings

# The three decision buckets. ``maybe`` is the gray zone M4 hands to Gemma.
KEEP = "keep"
MAYBE = "maybe"
REJECT = "reject"


@dataclass
class ScoreResult:
    """Per-image scoring outcome carried through dedup and export."""

    id: str
    path: str
    score: float | None  # final blended taste score in [0, 1]; None = gate-only
    decision: str  # one of KEEP / MAYBE / REJECT
    reasons: list[str] = field(default_factory=list)
    burst_id: int = 0
    embedding: np.ndarray | None = None


def blend_score(
    keep_prob: float | None, sim: float | None, cfg: ScoreSettings
) -> float | None:
    """Blend classifier keep-probability with taste-vector cosine similarity.

    The cosine similarity (in ``[-1, 1]``) is remapped to ``[0, 1]`` and combined
    with the keep-probability as a weighted mean. Whichever term is missing is
    dropped (its weight removed); if both are missing we return ``None`` so the
    caller falls back to a technical-gate-only decision.
    """
    terms: list[tuple[float, float]] = []  # (value, weight)
    if keep_prob is not None:
        terms.append((float(keep_prob), cfg.w_classifier))
    if sim is not None:
        terms.append(((float(sim) + 1.0) / 2.0, cfg.w_taste))
    if not terms:
        return None
    total_w = sum(w for _, w in terms)
    if total_w <= 0:
        # Degenerate weights -> unweighted mean of available terms.
        return float(np.mean([v for v, _ in terms]))
    return float(sum(v * w for v, w in terms) / total_w)


def decide(score: float | None, cfg: ScoreSettings) -> str:
    """Map a blended *score* to a keep/maybe/reject band.

    ``score >= keep_above`` keeps, ``score < reject_below`` rejects, the gray
    zone in between is ``maybe``. A ``None`` score (nothing to score on) is
    ``maybe`` — it cleared the technical gate but cannot be confidently sorted.
    """
    if score is None:
        return MAYBE
    if score >= cfg.keep_above:
        return KEEP
    if score < cfg.reject_below:
        return REJECT
    return MAYBE


def score_features(
    items: Sequence[dict],
    sharpness: dict[str, float],
    blink: dict[str, bool | None],
    classifier: KeepRejectModel | None,
    taste_vector: np.ndarray | None,
    sharpness_floor: float | None,
    cfg: ScoreSettings,
) -> list[ScoreResult]:
    """Score each item into a :class:`ScoreResult`.

    *items* are dicts with ``id`` / ``path`` / ``burst_id`` / ``embedding`` (and
    optionally precomputed classifier ``features``). The technical gate runs
    first: a detected blink or sub-floor sharpness is an immediate reject. Items
    that clear the gate get a blended taste score and a band decision.
    """
    results: list[ScoreResult] = []
    for item in items:
        iid = str(item["id"])
        reasons: list[str] = []

        # --- Technical gate (hard rejects, before any taste scoring) --------- #
        if blink.get(iid) is True:
            reasons.append("blink detected")
            results.append(_gated_reject(item, reasons))
            continue
        sharp = sharpness.get(iid)
        if sharpness_floor is not None and sharp is not None and sharp < sharpness_floor:
            reasons.append(f"soft focus (sharpness {sharp:.1f} < {sharpness_floor:.1f})")
            results.append(_gated_reject(item, reasons))
            continue

        # --- Taste score ----------------------------------------------------- #
        keep_prob = _keep_prob(classifier, item, sharp)
        sim = _similarity(taste_vector, item.get("embedding"))
        score = blend_score(keep_prob, sim, cfg)
        decision = decide(score, cfg)
        if score is None:
            reasons.append("gate-only (no taste model)")

        results.append(
            ScoreResult(
                id=iid,
                path=str(item["path"]),
                score=score,
                decision=decision,
                reasons=reasons,
                burst_id=int(item.get("burst_id", 0)),
                embedding=item.get("embedding"),
            )
        )
    return results


def _gated_reject(item: dict, reasons: list[str]) -> ScoreResult:
    return ScoreResult(
        id=str(item["id"]),
        path=str(item["path"]),
        score=None,
        decision=REJECT,
        reasons=reasons,
        burst_id=int(item.get("burst_id", 0)),
        embedding=item.get("embedding"),
    )


def _keep_prob(
    classifier: KeepRejectModel | None, item: dict, sharp: float | None
) -> float | None:
    """Classifier keep-probability, or ``None`` if there is no classifier."""
    if classifier is None:
        return None
    feat: dict[str, Any] = dict(item.get("features") or {})
    feat.setdefault("sharpness", sharp if sharp is not None else 0.0)
    return predict_proba(classifier, feat)


def _similarity(
    taste_vector: np.ndarray | None, embedding: np.ndarray | None
) -> float | None:
    """Cosine similarity to the taste_vector, or ``None`` if either is missing."""
    if taste_vector is None or embedding is None:
        return None
    return similarity(np.asarray(embedding), np.asarray(taste_vector))
