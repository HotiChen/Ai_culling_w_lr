from __future__ import annotations

from pathlib import Path

import pytest

from photovault.core.learn import learn_from_folder
from photovault.core.profile import load_profile
from photovault.settings import Settings


def test_collect_catalogs_multi_and_dedup(catalog_folder: Path, tmp_path: Path):
    from photovault.core.learn.pipeline import collect_catalogs
    from photovault.tests.make_fake import default_images, write_catalog

    folder2 = tmp_path / "more"
    folder2.mkdir()
    write_catalog(folder2 / "shoot2.lrcat", default_images())

    # Single folder -> 1; two folders -> 2; passing the same root twice dedups.
    assert len(collect_catalogs(catalog_folder)) == 1
    assert len(collect_catalogs([catalog_folder, folder2])) == 2
    assert len(collect_catalogs([catalog_folder, catalog_folder])) == 1


def test_learn_from_multiple_folders(catalog_folder: Path, settings: Settings, tmp_path: Path):
    from photovault.tests.make_fake import default_images, write_catalog

    folder2 = tmp_path / "more"
    folder2.mkdir()
    write_catalog(folder2 / "shoot2.lrcat", default_images())

    report = learn_from_folder([catalog_folder, folder2], "multi", settings, use_llm=False)
    assert report.n_catalogs == 2
    assert report.n_images == 22  # 11 per identical catalog


def test_learn_end_to_end(catalog_folder: Path, settings: Settings):
    report = learn_from_folder(catalog_folder, "熱茶", settings, use_llm=False)

    assert report.n_catalogs == 1
    assert report.n_images == 11
    assert report.n_keepers == 6
    assert report.n_rejects == 4
    assert report.n_presets >= 1
    assert report.llm_used is False

    # Profile is persisted and reloadable.
    prof = load_profile(settings.profiles_dir, "熱茶")
    assert prof.meta.n_images == 11
    assert prof.thresholds.keep_rate == round(6 / 10, 3)
    assert (prof.path / "labels.csv").exists()
    assert len(prof.preset_files) >= 1


def test_learn_llm_unavailable_falls_back(catalog_folder: Path, tmp_path: Path):
    # LLM enabled but pointed at a dead port -> placeholder profile.md, no crash.
    s = Settings(profiles_dir=tmp_path / "profiles")
    s.llm.enabled = True
    s.llm.host = "http://127.0.0.1:1"
    s.llm.request_timeout_s = 1.0

    report = learn_from_folder(catalog_folder, "p", s, use_llm=True)
    assert report.llm_used is False
    assert "unavailable" in report.llm_note.lower()


def test_learn_no_catalogs(tmp_path: Path, settings: Settings):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError):
        learn_from_folder(empty, "p", settings, use_llm=False)
