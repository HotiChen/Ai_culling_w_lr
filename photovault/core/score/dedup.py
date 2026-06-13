"""Burst near-duplicate de-duplication (M3).

Within each burst we cluster frames by pHash proximity (single-link with a
configurable hamming radius), keep the top-K by score per cluster, and demote
the rest to ``reject`` with a "near-duplicate" reason. K is derived from the
profile's historical ``burst_keep_rate`` (rounded up, never below 1) so the
machine keeps roughly as many frames per burst as you historically did.

Only frames currently in a non-reject state participate — frames already gated
out by :mod:`photovault.core.score.engine` are never revived.
"""

from __future__ import annotations

import math
from typing import Mapping

from photovault.core.features.phash import hamming
from photovault.core.score.engine import REJECT, ScoreResult
from photovault.settings import ScoreSettings


def keep_k(burst_size: int, burst_keep_rate: float) -> int:
    """How many frames to keep from a burst of *burst_size*.

    ``ceil(burst_size * burst_keep_rate)`` clamped to ``[1, burst_size]``.
    """
    k = math.ceil(burst_size * max(0.0, burst_keep_rate))
    return max(1, min(k, burst_size))


def dedup_bursts(
    results: list[ScoreResult],
    hashes: Mapping[str, int],
    burst_keep_rate: float,
    cfg: ScoreSettings,
) -> list[ScoreResult]:
    """Demote near-duplicate burst frames beyond the keep-K to ``reject``.

    Mutates and returns *results*. Clusters of frames within
    ``cfg.phash_hamming_max`` hamming distance keep their top-K (by score);
    losers become ``reject`` with reason ``"near-duplicate"``.
    """
    by_burst: dict[int, list[ScoreResult]] = {}
    for r in results:
        by_burst.setdefault(r.burst_id, []).append(r)

    for frames in by_burst.values():
        live = [f for f in frames if f.decision != REJECT]
        if len(live) < 2:
            continue  # nothing to dedup against
        k = keep_k(len(frames), burst_keep_rate)
        for cluster in _cluster(live, hashes, cfg.phash_hamming_max):
            if len(cluster) <= 1:
                continue
            # Best-first; keep the top-K, demote the tail as near-duplicates.
            cluster.sort(key=lambda f: (f.score is not None, f.score or 0.0), reverse=True)
            for loser in cluster[k:]:
                loser.decision = REJECT
                loser.reasons.append("near-duplicate")
    return results


def _cluster(
    frames: list[ScoreResult], hashes: Mapping[str, int], hamming_max: int
) -> list[list[ScoreResult]]:
    """Single-link cluster frames whose pHashes lie within *hamming_max*.

    Frames missing a hash (or all when ``hamming_max`` separates them) each form
    their own singleton cluster so they are never treated as duplicates.
    """
    clusters: list[list[ScoreResult]] = []
    for frame in frames:
        h = hashes.get(frame.id)
        placed = False
        if h is not None:
            for cluster in clusters:
                if any(
                    hashes.get(m.id) is not None
                    and hamming(h, hashes[m.id]) <= hamming_max
                    for m in cluster
                ):
                    cluster.append(frame)
                    placed = True
                    break
        if not placed:
            clusters.append([frame])
    return clusters
