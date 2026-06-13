"""Ollama client wrapping a single multimodal Gemma model.

Design (ARCHITECTURE.md §2): the LLM is a *pluggable, explainable arbiter*,
never a per-image bottleneck. One Gemma 3 12B model does both jobs because it
is multimodal:

  * stage A — :meth:`write_profile` turns L1/L2/L3 stats into ``profile.md``
  * stage B — :meth:`arbitrate` looks at a single gray-zone image + the
    rule-book and returns a keep/reject verdict with a one-line reason

The HTTP call uses only the standard library (``urllib``) so M1 has zero extra
dependencies. If Ollama is not reachable, callers get :class:`JudgeUnavailable`
and the pipeline falls back to pure CV+CLIP — the system runs without an LLM.
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
    """Thin wrapper over Ollama's ``/api/generate`` endpoint."""

    def __init__(self, cfg: LLMSettings):
        self.cfg = cfg

    # -- low-level -------------------------------------------------------- #
    def _generate(self, prompt: str, images: list[str] | None = None) -> str:
        if not self.cfg.enabled:
            raise JudgeUnavailable("LLM disabled in settings")

        payload: dict = {
            "model": self.cfg.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self.cfg.temperature},
        }
        if images:
            payload["images"] = images  # base64-encoded, multimodal Gemma

        url = self.cfg.host.rstrip("/") + "/api/generate"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.cfg.request_timeout_s) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise JudgeUnavailable(f"cannot reach Ollama at {url}: {exc}") from exc
        return body.get("response", "")

    @staticmethod
    def _encode_image(path: str | Path) -> str:
        return base64.b64encode(Path(path).read_bytes()).decode("ascii")

    # -- stage A: rule-book ---------------------------------------------- #
    def write_profile(self, name: str, stats: dict) -> str:
        """Generate the human-readable taste rule-book (``profile.md``)."""
        prompt = build_profile_prompt(name, stats)
        return self._generate(prompt)

    # -- stage B: gray-zone arbitration ---------------------------------- #
    def arbitrate(self, image_path: str | Path, rule_book: str) -> Verdict:
        """Decide keep/reject for one ambiguous image, with a reason."""
        prompt = build_arbitration_prompt(rule_book)
        raw = self._generate(prompt, images=[self._encode_image(image_path)])
        return parse_verdict(raw)


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
