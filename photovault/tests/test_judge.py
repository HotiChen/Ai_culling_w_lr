from __future__ import annotations

import io
import json
import urllib.error

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
    parse_openai_models,
    parse_openai_response,
    parse_ollama_response,
    parse_ollama_tags,
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


# --------------------------------------------------------------------------- #
# Diagnostics: is the server up, and is the configured Gemma tag actually there?
#
# Without this, a wrong model tag (e.g. `gemma4:12b` when the machine only has
# `gemma3:12b` pulled) fails as a bare "HTTP Error 404" and the pipeline
# silently falls back to a placeholder profile.md — the user never learns why.
# --------------------------------------------------------------------------- #
def _fake_urlopen_error(status: int, body: dict):
    """urlopen stand-in that raises HTTPError carrying a JSON error body."""

    def fake(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, status, "Not Found", {},
            io.BytesIO(json.dumps(body).encode("utf-8")),
        )

    return fake


def _fake_urlopen_get(captured: dict, response_body: dict):
    """urlopen stand-in for GET requests (no request body to decode)."""

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=None):
        captured["url"] = req.full_url
        return _Resp(json.dumps(response_body).encode("utf-8"))

    return fake


def test_http_error_body_surfaces_in_message(monkeypatch):
    monkeypatch.setattr(
        ollama_client.urllib.request, "urlopen",
        _fake_urlopen_error(404, {"error": "model 'gemma4:12b' not found, try pulling it first"}),
    )
    judge = GemmaJudge(LLMSettings(backend="ollama"))
    with pytest.raises(JudgeUnavailable) as exc:
        judge.write_profile("p", {})
    msg = str(exc.value)
    assert "404" in msg
    # The server's own explanation must reach the user, not just the status code.
    assert "not found" in msg and "gemma4:12b" in msg


def test_parse_model_lists():
    assert parse_ollama_tags({"models": [{"name": "gemma4:12b"}, {"name": "llava:7b"}]}) == [
        "gemma4:12b",
        "llava:7b",
    ]
    assert parse_ollama_tags({}) == []
    assert parse_openai_models({"data": [{"id": "gemma-4-12b-qat"}]}) == ["gemma-4-12b-qat"]
    assert parse_openai_models({}) == []


def test_list_models_ollama_hits_tags_endpoint(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        ollama_client.urllib.request, "urlopen",
        _fake_urlopen_get(captured, {"models": [{"name": "gemma4:12b"}]}),
    )
    models = GemmaJudge(LLMSettings(backend="ollama", host="http://localhost:11434")).list_models()
    assert captured["url"].endswith("/api/tags")
    assert models == ["gemma4:12b"]


def test_list_models_llamacpp_hits_v1_models(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        ollama_client.urllib.request, "urlopen",
        _fake_urlopen_get(captured, {"data": [{"id": "gemma-4-12b"}]}),
    )
    models = GemmaJudge(LLMSettings(backend="llamacpp", host="http://127.0.0.1:8085")).list_models()
    assert captured["url"].endswith("/v1/models")
    assert models == ["gemma-4-12b"]


def test_status_model_present(monkeypatch):
    monkeypatch.setattr(
        ollama_client.urllib.request, "urlopen",
        _fake_urlopen_get({}, {"models": [{"name": "gemma4:12b"}, {"name": "gemma3:12b"}]}),
    )
    st = GemmaJudge(LLMSettings(model="gemma4:12b")).status()
    assert st.reachable is True
    assert st.model_present is True
    assert "gemma4:12b" in st.models
    assert st.ok is True


def test_status_model_missing_suggests_pull_and_lists_installed(monkeypatch):
    monkeypatch.setattr(
        ollama_client.urllib.request, "urlopen",
        _fake_urlopen_get({}, {"models": [{"name": "gemma3:12b"}]}),
    )
    st = GemmaJudge(LLMSettings(model="gemma4:12b")).status()
    assert st.reachable is True
    assert st.model_present is False
    assert st.ok is False
    assert "gemma3:12b" in st.detail        # show what IS installed
    assert "ollama pull gemma4:12b" in st.detail   # and how to fix it


def test_status_matches_latest_suffix(monkeypatch):
    # Ollama reports bare `gemma4` pulls as `gemma4:latest`; configuring
    # `gemma4` must still count as present.
    monkeypatch.setattr(
        ollama_client.urllib.request, "urlopen",
        _fake_urlopen_get({}, {"models": [{"name": "gemma4:latest"}]}),
    )
    st = GemmaJudge(LLMSettings(model="gemma4")).status()
    assert st.model_present is True


def test_status_unreachable_is_not_an_exception():
    cfg = LLMSettings(host="http://127.0.0.1:1", request_timeout_s=1.0)
    st = GemmaJudge(cfg).status()
    assert st.reachable is False
    assert st.ok is False
    assert st.models == []
    assert "127.0.0.1:1" in st.detail


def test_status_disabled():
    st = GemmaJudge(LLMSettings(enabled=False)).status()
    assert st.ok is False
    assert "disabled" in st.detail.lower()
