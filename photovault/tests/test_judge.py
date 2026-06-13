from __future__ import annotations

import pytest

from photovault.core.judge.ollama_client import (
    GemmaJudge,
    JudgeUnavailable,
    Verdict,
    build_arbitration_prompt,
    build_profile_prompt,
    parse_verdict,
)
from photovault.settings import LLMSettings


def test_default_model_is_gemma():
    cfg = LLMSettings()
    assert cfg.model == "gemma3:12b"


def test_build_profile_prompt_contains_stats():
    prompt = build_profile_prompt("熱茶", {"keep_rate": 0.6})
    assert "熱茶" in prompt
    assert "keep_rate" in prompt


def test_build_arbitration_prompt_demands_json():
    prompt = build_arbitration_prompt("be picky about focus")
    assert "JSON" in prompt
    assert "be picky about focus" in prompt


def test_parse_verdict_clean_json():
    v = parse_verdict('{"keep": true, "reason": "sharp eyes"}')
    assert v.keep is True
    assert v.reason == "sharp eyes"


def test_parse_verdict_with_prose():
    v = parse_verdict('Sure! {"keep": false, "reason": "subject blinked"} hope that helps')
    assert v.keep is False
    assert v.reason == "subject blinked"


def test_parse_verdict_fallback():
    v = parse_verdict("I would keep this one")
    assert v.keep is True
    assert isinstance(v, Verdict)


def test_disabled_raises():
    judge = GemmaJudge(LLMSettings(enabled=False))
    with pytest.raises(JudgeUnavailable):
        judge.write_profile("p", {})


def test_unreachable_host_raises():
    # Point at a closed port; should fail fast as JudgeUnavailable, not crash.
    cfg = LLMSettings(enabled=True, host="http://127.0.0.1:1", request_timeout_s=1.0)
    judge = GemmaJudge(cfg)
    with pytest.raises(JudgeUnavailable):
        judge.write_profile("p", {"keep_rate": 0.5})
