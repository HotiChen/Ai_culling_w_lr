from __future__ import annotations

import io
import json

import pytest

from photovault.core.judge import ollama_client
from photovault.core.judge.ollama_client import (
    GemmaJudge,
    JudgeUnavailable,
    Verdict,
    build_arbitration_prompt,
    build_ollama_payload,
    build_openai_payload,
    build_profile_prompt,
    parse_openai_response,
    parse_ollama_response,
    parse_verdict,
)
from photovault.settings import LLMSettings


def test_default_model_is_gemma():
    cfg = LLMSettings()
    assert cfg.model == "gemma4:12b"


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


# --------------------------------------------------------------------------- #
# Backend selection: ollama vs llama.cpp (OpenAI-compatible)
# --------------------------------------------------------------------------- #
def test_default_backend_is_ollama():
    assert LLMSettings().backend == "ollama"


def test_backend_validation_rejects_unknown():
    with pytest.raises(Exception):
        LLMSettings(backend="vllm")


def test_build_ollama_payload_shape():
    p = build_ollama_payload("gemma4:12b", "hi", 0.2, ["BASE64DATA"])
    assert p["model"] == "gemma4:12b"
    assert p["prompt"] == "hi"
    assert p["stream"] is False
    assert p["images"] == ["BASE64DATA"]
    # No images -> no images key.
    assert "images" not in build_ollama_payload("m", "hi", 0.2, [])


def test_build_openai_payload_shape():
    p = build_openai_payload("gemma4:12b", "hi", 0.2, ["data:image/jpeg;base64,XX"])
    msg = p["messages"][0]
    assert msg["role"] == "user"
    assert msg["content"][0] == {"type": "text", "text": "hi"}
    assert msg["content"][1]["type"] == "image_url"
    assert msg["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_parse_responses():
    assert parse_ollama_response({"response": "ok"}) == "ok"
    assert parse_ollama_response({}) == ""
    body = {"choices": [{"message": {"content": "hello"}}]}
    assert parse_openai_response(body) == "hello"
    assert parse_openai_response({"choices": []}) == ""


def _fake_urlopen(captured: dict, response_body: dict):
    """Return a urlopen stand-in that records the request and replies JSON."""

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=None):
        captured["url"] = req.full_url
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return _Resp(json.dumps(response_body).encode("utf-8"))

    return fake


def test_dispatch_ollama_hits_generate_endpoint(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        ollama_client.urllib.request, "urlopen",
        _fake_urlopen(captured, {"response": '{"keep": true, "reason": "nice"}'}),
    )
    cfg = LLMSettings(backend="ollama", host="http://localhost:11434")
    out = GemmaJudge(cfg)._generate("prompt-text")
    assert captured["url"].endswith("/api/generate")
    assert captured["payload"]["prompt"] == "prompt-text"
    assert out == '{"keep": true, "reason": "nice"}'


def test_dispatch_llamacpp_hits_openai_endpoint(monkeypatch):
    captured: dict = {}
    body = {"choices": [{"message": {"content": "from llamacpp"}}]}
    monkeypatch.setattr(
        ollama_client.urllib.request, "urlopen", _fake_urlopen(captured, body)
    )
    cfg = LLMSettings(backend="llamacpp", host="http://127.0.0.1:8085")
    out = GemmaJudge(cfg)._generate("prompt-text")
    assert captured["url"].endswith("/v1/chat/completions")
    assert captured["payload"]["messages"][0]["content"][0]["text"] == "prompt-text"
    assert out == "from llamacpp"


def test_arbitrate_llamacpp_sends_image_data_url(monkeypatch, tmp_path):
    img = tmp_path / "x.jpg"
    img.write_bytes(b"\xff\xd8\xff\xd9")  # minimal JPEG-ish bytes
    captured: dict = {}
    body = {"choices": [{"message": {"content": '{"keep": false, "reason": "soft"}'}}]}
    monkeypatch.setattr(
        ollama_client.urllib.request, "urlopen", _fake_urlopen(captured, body)
    )
    cfg = LLMSettings(backend="llamacpp", host="http://127.0.0.1:8085")
    verdict = GemmaJudge(cfg).arbitrate(img, "rule book")
    content = captured["payload"]["messages"][0]["content"]
    assert any(
        c["type"] == "image_url" and c["image_url"]["url"].startswith("data:image/jpeg;base64,")
        for c in content
    )
    assert verdict.keep is False
    assert verdict.reason == "soft"
