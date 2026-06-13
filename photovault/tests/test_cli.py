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


def test_apply_not_implemented(env, catalog_folder: Path):
    result = runner.invoke(app, ["apply", str(catalog_folder), "--name", "熱茶"])
    assert result.exit_code == 2
    assert "M3" in result.output
