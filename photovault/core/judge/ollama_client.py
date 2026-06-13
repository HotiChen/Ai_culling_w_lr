"""Local-LLM client wrapping a single multimodal Gemma model.

Design (ARCHITECTURE.md §2): the LLM is a *pluggable, explainable arbiter*,
never a per-image bottleneck. One Gemma 4 12B model does both jobs because it
is multimodal:

  * stage A — :meth:`write_profile` turns L1/L2/L3 stats into ``profile.md``
  * stage B — :meth:`arbitrate` looks at a single gray-zone image + the
    rule-book and returns a keep/reject verdict with a one-line reason

Two server backends are supported, selected by ``LLMSettings.backend``:

  * ``ollama``   — Ollama's ``/api/generate`` (images as raw base64)
  * ``llamacpp`` — a llama.cpp server's OpenAI-compatible
    ``/v1/chat/completions`` (images as ``data:`` URLs). This matches a local
    Gemma 4 12B QAT + MTP + mmproj deployment (e.g. port 8085).

The HTTP call uses only the standard library (``urllib``) so there are zero
extra dependencies. If the server is unreachable, callers get
:class:`JudgeUnavailable` and the pipeline falls back to pure CV+CLIP — the
system runs without an LLM.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from photovault.settings import LLMSettings


class JudgeUnavailable(RuntimeError):
    """Raised when the local LLM cannot be reached or is disabled."""


@dataclass
class Verdict:
    keep: bool
    reason: str
    raw: str = ""


class GemmaJudge:
    """Backend-agnostic wrapper over a local Gemma server (Ollama or llama.cpp)."""

    def __init__(self, cfg: LLMSettings):
        self.cfg = cfg

    # -- low-level -------------------------------------------------------- #
    def _generate(self, prompt: str, image_paths: list[str | Path] | None = None) -> str:
        if not self.cfg.enabled:
            raise JudgeUnavailable("LLM disabled in settings")

        if self.cfg.backend == "llamacpp":
            url = self.cfg.host.rstrip("/") + "/v1/chat/completions"
            payload = build_openai_payload(
                self.cfg.model, prompt, self.cfg.temperature,
                [_data_url(p) for p in (image_paths or [])],
            )
            body = self._post(url, payload)
            return parse_openai_response(body)

        # Default: Ollama.
        url = self.cfg.host.rstrip("/") + "/api/generate"
        payload = build_ollama_payload(
            self.cfg.model, prompt, self.cfg.temperature,
            [_encode_image(p) for p in (image_paths or [])],
        )
        body = self._post(url, payload)
        return parse_ollama_response(body)

    def _post(self, url: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.request_timeout_s) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise JudgeUnavailable(
                f"cannot reach {self.cfg.backend} server at {url}: {exc}"
            ) from exc

    # -- stage A: rule-book ---------------------------------------------- #
    def write_profile(self, name: str, stats: dict) -> str:
        """Generate the human-readable taste rule-book (``profile.md``)."""
        prompt = build_profile_prompt(name, stats)
        return self._generate(prompt)

    # -- stage B: gray-zone arbitration ---------------------------------- #
    def arbitrate(self, image_path: str | Path, rule_book: str) -> Verdict:
        """Decide keep/reject for one ambiguous image, with a reason."""
        prompt = build_arbitration_prompt(rule_book)
        raw = self._generate(prompt, image_paths=[image_path])
        return parse_verdict(raw)


# --------------------------------------------------------------------------- #
# Image encoding + request/response shaping (pure, independently testable)
# --------------------------------------------------------------------------- #
def _encode_image(path: str | Path) -> str:
    """Raw base64 of an image file (Ollama's ``images`` format)."""
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def _mime_for(path: str | Path) -> str:
    ext = Path(path).suffix.lower()
    return {
        ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif",
    }.get(ext, "image/jpeg")


def _data_url(path: str | Path) -> str:
    """``data:`` URL of an image file (OpenAI/llama.cpp ``image_url`` format)."""
    return f"data:{_mime_for(path)};base64,{_encode_image(path)}"


def build_ollama_payload(
    model: str, prompt: str, temperature: float, images_b64: list[str]
) -> dict:
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    if images_b64:
        payload["images"] = images_b64
    return payload


def build_openai_payload(
    model: str, prompt: str, temperature: float, image_data_urls: list[str]
) -> dict:
    """OpenAI-compatible chat payload (llama.cpp ``/v1/chat/completions``)."""
    content: list[dict] = [{"type": "text", "text": prompt}]
    for url in image_data_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})
    return {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": temperature,
        "stream": False,
    }


def parse_ollama_response(body: dict) -> str:
    return body.get("response", "")


def parse_openai_response(body: dict) -> str:
    choices = body.get("choices") or []
    if not choices:
        return ""
    return (choices[0].get("message") or {}).get("content", "")


# --------------------------------------------------------------------------- #
# Prompt builders (pure functions — independently testable)
# --------------------------------------------------------------------------- #
def build_profile_prompt(name: str, stats: dict) -> str:
    return (
        "You are a photo editor's assistant. Below are statistics summarizing a "
        f"photographer's culling and develop choices (profile '{name}'). Write a "
        "concise, first-person taste rule-book in Markdown describing their "
        "preferences (aperture/ISO/focal tendencies, burst keep behavior, look). "
        "This rule-book will later be used as a system prompt to cull new photos.\n\n"
        "STATISTICS (JSON):\n"
        f"{json.dumps(stats, ensure_ascii=False, indent=2)}\n"
    )


def build_arbitration_prompt(rule_book: str) -> str:
    return (
        "You are culling photos for an editor whose taste is described below. "
        "Look at the attached image and decide whether to KEEP or REJECT it. "
        "Respond as strict JSON: {\"keep\": true|false, \"reason\": \"<one line>\"}.\n\n"
        "EDITOR'S TASTE RULE-BOOK:\n"
        f"{rule_book}\n"
    )


def parse_verdict(raw: str) -> Verdict:
    """Parse the model's JSON reply; tolerant of surrounding prose."""
    text = raw.strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            return Verdict(
                keep=bool(obj.get("keep", False)),
                reason=str(obj.get("reason", "")).strip(),
                raw=raw,
            )
        except json.JSONDecodeError:
            pass
    # Fallback heuristic.
    keep = "keep" in text.lower() and "reject" not in text.lower()
    return Verdict(keep=keep, reason=text[:120], raw=raw)
