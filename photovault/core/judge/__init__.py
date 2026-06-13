"""Local LLM arbiter (Ollama + Gemma): rule-book generation + gray-zone vision."""

from photovault.core.judge.ollama_client import (
    GemmaJudge,
    JudgeUnavailable,
    Verdict,
)

__all__ = ["GemmaJudge", "JudgeUnavailable", "Verdict"]
