"""M3: the new ScoreSettings block, and that it stays env-overridable."""

from __future__ import annotations

from photovault.settings import ScoreSettings, Settings


def test_score_defaults_present():
    s = Settings()
    assert isinstance(s.score, ScoreSettings)
    # Bands are ordered so there is a real gray zone between them.
    assert s.score.reject_below <= s.score.keep_above
    assert s.score.w_classifier >= 0 and s.score.w_taste >= 0
    assert 0 <= s.score.phash_hamming_max <= 64


def test_score_env_override(monkeypatch):
    monkeypatch.setenv("PHOTOVAULT_SCORE__KEEP_ABOVE", "0.8")
    monkeypatch.setenv("PHOTOVAULT_SCORE__REJECT_BELOW", "0.3")
    monkeypatch.setenv("PHOTOVAULT_SCORE__PHASH_HAMMING_MAX", "12")
    s = Settings()
    assert s.score.keep_above == 0.8
    assert s.score.reject_below == 0.3
    assert s.score.phash_hamming_max == 12
