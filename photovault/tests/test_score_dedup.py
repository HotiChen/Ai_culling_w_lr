"""M3: burst near-duplicate de-duplication keyed on pHash + score + keep-rate."""

from __future__ import annotations

from photovault.core.score.dedup import dedup_bursts, keep_k
from photovault.core.score.engine import ScoreResult
from photovault.settings import ScoreSettings


def _res(rid: str, burst: int, score: float, decision: str = "keep") -> ScoreResult:
    return ScoreResult(
        id=rid,
        path=f"{rid}.jpg",
        score=score,
        decision=decision,
        reasons=[],
        burst_id=burst,
        embedding=None,
    )


def test_keep_k_rounds_up_min_one():
    assert keep_k(5, 0.4) == 2  # ceil(2.0) -> 2
    assert keep_k(5, 0.41) == 3  # ceil(2.05) -> 3
    assert keep_k(5, 0.0) == 1  # never below 1
    assert keep_k(1, 0.9) == 1


def test_dedup_demotes_near_duplicates_beyond_k():
    cfg = ScoreSettings(phash_hamming_max=8)
    # 4 near-duplicate frames in one burst (hashes within hamming 8).
    base = 0b0
    hashes = {"a": base, "b": base | 0b1, "c": base | 0b11, "d": base | 0b111}
    results = [
        _res("a", 0, 0.9),
        _res("b", 0, 0.8),
        _res("c", 0, 0.7),
        _res("d", 0, 0.6),
    ]
    # burst_keep_rate 0.5 of 4 frames -> keep_k = 2.
    out = dedup_bursts(results, hashes, burst_keep_rate=0.5, cfg=cfg)
    by_id = {r.id: r for r in out}
    # Top-2 by score survive; the rest are demoted to reject as near-duplicates.
    assert by_id["a"].decision == "keep"
    assert by_id["b"].decision == "keep"
    assert by_id["c"].decision == "reject"
    assert by_id["d"].decision == "reject"
    assert any("duplicate" in r.lower() for r in by_id["c"].reasons)


def test_dedup_keeps_distinct_frames_in_same_burst():
    cfg = ScoreSettings(phash_hamming_max=4)
    # Two clusters of distinct images (far apart in hamming) in one burst.
    hashes = {"a": 0b0, "b": 0b1, "c": 0xFFFF, "d": 0xFFFE}
    results = [_res("a", 0, 0.9), _res("b", 0, 0.8), _res("c", 0, 0.7), _res("d", 0, 0.6)]
    out = dedup_bursts(results, hashes, burst_keep_rate=0.5, cfg=cfg)
    by_id = {r.id: r for r in out}
    # Each cluster keeps its own best; cross-cluster frames are not duplicates.
    assert by_id["a"].decision == "keep"  # best of cluster {a,b}
    assert by_id["c"].decision == "keep"  # best of cluster {c,d}


def test_dedup_does_not_revive_gate_rejects():
    cfg = ScoreSettings(phash_hamming_max=8)
    hashes = {"a": 0, "b": 1}
    results = [
        _res("a", 0, 0.9, decision="reject"),  # already gated out
        _res("b", 0, 0.5, decision="maybe"),
    ]
    out = dedup_bursts(results, hashes, burst_keep_rate=1.0, cfg=cfg)
    by_id = {r.id: r for r in out}
    assert by_id["a"].decision == "reject"  # stays rejected
    assert by_id["b"].decision == "maybe"  # untouched (only 1 live frame)


def test_singleton_burst_untouched():
    cfg = ScoreSettings(phash_hamming_max=8)
    results = [_res("a", 0, 0.5, decision="maybe"), _res("b", 1, 0.9, decision="keep")]
    out = dedup_bursts(results, {"a": 0, "b": 99}, burst_keep_rate=0.1, cfg=cfg)
    by_id = {r.id: r for r in out}
    assert by_id["a"].decision == "maybe"
    assert by_id["b"].decision == "keep"
