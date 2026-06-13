"""M3: self-contained HTML review report."""

from __future__ import annotations

from pathlib import Path

from photovault.core.export.report import write_report
from photovault.core.score.engine import ScoreResult


def _res(rid: str, decision: str, score, reasons=None) -> ScoreResult:
    return ScoreResult(
        id=rid,
        path=f"/photos/{rid}.jpg",
        score=score,
        decision=decision,
        reasons=reasons or [],
        burst_id=0,
        embedding=None,
    )


def test_report_lists_every_image_and_decision(tmp_path: Path):
    results = [
        _res("alpha", "keep", 0.91),
        _res("beta", "maybe", 0.5),
        _res("gamma", "reject", 0.1, reasons=["blink"]),
    ]
    out = write_report(results, tmp_path / "report.html")
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert html.lstrip().lower().startswith("<!doctype html")
    for r in results:
        assert r.id in html
        assert r.decision in html
    assert "blink" in html
    # Counts summary present.
    assert "keep" in html and "maybe" in html and "reject" in html


def test_report_handles_none_score(tmp_path: Path):
    out = write_report([_res("g", "maybe", None)], tmp_path / "r.html")
    html = out.read_text(encoding="utf-8")
    assert "g" in html  # does not crash on a gate-only (scoreless) row


def test_report_is_self_contained(tmp_path: Path):
    out = write_report([_res("a", "keep", 0.8)], tmp_path / "r.html")
    html = out.read_text(encoding="utf-8")
    # No external CSS/JS references — everything inline.
    assert "http://" not in html.replace("http://www.w3.org", "")
    assert "<link" not in html
