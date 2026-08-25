from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from photovault.cli.main import app

runner = CliRunner()


@pytest.fixture
def env(monkeypatch, tmp_path: Path):
    """Isolate profiles dir + disable LLM via env vars the CLI reads."""
    monkeypatch.setenv("PHOTOVAULT_PROFILES_DIR", str(tmp_path / "profiles"))
    monkeypatch.setenv("PHOTOVAULT_LLM__ENABLED", "false")
    return tmp_path


def test_learn_and_inspect(env, catalog_folder: Path):
    result = runner.invoke(
        app, ["learn", str(catalog_folder), "--name", "熱茶", "--no-llm"]
    )
    assert result.exit_code == 0, result.output
    assert "Learned profile" in result.output
    assert "images      : 11" in result.output

    result = runner.invoke(app, ["inspect", "--name", "熱茶"])
    assert result.exit_code == 0, result.output
    assert "Profile: 熱茶" in result.output
    assert "keep_rate" in result.output


def test_inspect_missing(env):
    result = runner.invoke(app, ["inspect", "--name", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_apply_runs_stage_b(env, catalog_folder: Path, new_photos: Path):
    pytest.importorskip("PIL")
    # Learn an M1-only profile so apply has something to load without an embedder.
    learn = runner.invoke(
        app, ["learn", str(catalog_folder), "--name", "熱茶", "--no-llm"]
    )
    assert learn.exit_code == 0, learn.output

    result = runner.invoke(
        app, ["apply", str(new_photos), "--name", "熱茶", "--no-llm", "--no-report"]
    )
    assert result.exit_code == 0, result.output
    assert "keep" in result.output.lower()
    assert "maybe" in result.output.lower()
    assert "reject" in result.output.lower()


def test_apply_missing_profile(env, new_photos: Path):
    pytest.importorskip("PIL")
    result = runner.invoke(app, ["apply", str(new_photos), "--name", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()


# --------------------------------------------------------------------------- #
# `photovault doctor` — is the local Gemma actually reachable, with the right tag?
# --------------------------------------------------------------------------- #
def test_doctor_reports_ready(monkeypatch, tmp_path: Path):
    from photovault.core.judge.ollama_client import LLMStatus

    monkeypatch.setenv("PHOTOVAULT_PROFILES_DIR", str(tmp_path / "profiles"))
    monkeypatch.setattr(
        "photovault.core.judge.GemmaJudge.status",
        lambda self: LLMStatus(True, True, ["gemma4:12b"], "ollama has 'gemma4:12b'"),
    )
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0, result.output
    assert "gemma4:12b" in result.output
    assert "ready" in result.output.lower()


def test_doctor_reports_missing_model_and_exits_nonzero(monkeypatch, tmp_path: Path):
    from photovault.core.judge.ollama_client import LLMStatus

    monkeypatch.setenv("PHOTOVAULT_PROFILES_DIR", str(tmp_path / "profiles"))
    monkeypatch.setattr(
        "photovault.core.judge.GemmaJudge.status",
        lambda self: LLMStatus(
            True, False, ["gemma3:12b"],
            "model 'gemma4:12b' is not available. Installed: gemma3:12b. "
            "Fix with: ollama pull gemma4:12b",
        ),
    )
    result = runner.invoke(app, ["doctor"])
    # Non-zero so scripts/CI can gate on it, but the pipeline itself still runs.
    assert result.exit_code == 1
    assert "ollama pull gemma4:12b" in result.output
    # Culling without an LLM is supported, so say so instead of just failing.
    assert "--no-llm" in result.output
