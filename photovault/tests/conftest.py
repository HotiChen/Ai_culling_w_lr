"""Shared pytest fixtures: a synthetic catalog folder and settings."""

from __future__ import annotations

from pathlib import Path

import pytest

from photovault.settings import Settings
from photovault.tests.make_fake import default_images, write_catalog


@pytest.fixture
def catalog_folder(tmp_path: Path) -> Path:
    """A folder containing one synthetic ``.lrcat`` built from default_images()."""
    folder = tmp_path / "catalogs"
    folder.mkdir()
    write_catalog(folder / "shoot.lrcat", default_images())
    return folder


@pytest.fixture
def catalog_path(catalog_folder: Path) -> Path:
    return catalog_folder / "shoot.lrcat"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointing profiles at an isolated temp dir, LLM disabled."""
    s = Settings(profiles_dir=tmp_path / "profiles")
    s.llm.enabled = False  # tests never hit a real Ollama server
    return s
