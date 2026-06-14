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


def test_has_curation_signal_and_filtered_read(catalog_folder: Path, tmp_path: Path):
    from photovault.core.learn.pipeline import (
        has_curation_signal,
        read_catalogs_filtered,
    )
    from photovault.tests.make_fake import FakeImage, default_images, write_catalog

    # A catalog where nothing was picked / rated / color-labelled.
    blank = tmp_path / "blank"
    blank.mkdir()
    write_catalog(
        blank / "blank.lrcat",
        [FakeImage(base_name=f"x{i}", capture_time=f"2024-01-01T00:00:0{i}") for i in range(3)],
    )
    blank_cat = blank / "blank.lrcat"
    good_cat = catalog_folder / "shoot.lrcat"

    from photovault.core.catalog.reader import iter_images, open_ro

    conn = open_ro(blank_cat)
    assert not has_curation_signal(list(iter_images(conn)))
    conn.close()

    images, kept, skipped = read_catalogs_filtered([good_cat, blank_cat])
    assert kept == [good_cat]
    assert len(skipped) == 1 and skipped[0][0] == blank_cat
    assert len(images) == 11  # only the good catalog's images


def test_learn_skips_unlabeled_catalog_and_logs(catalog_folder: Path, settings: Settings, tmp_path: Path):
    from photovault.tests.make_fake import FakeImage, write_catalog

    # Put a blank (no-signal) catalog alongside the good one under one root.
    blank_dir = tmp_path / "roots"
    blank_dir.mkdir()
    write_catalog(
        blank_dir / "blank.lrcat",
        [FakeImage(base_name=f"x{i}", capture_time=f"2024-01-01T00:00:0{i}") for i in range(3)],
    )

    report = learn_from_folder(
        [catalog_folder, blank_dir], "mix", settings, use_llm=False
    )
    assert report.n_catalogs == 1  # blank one skipped
    assert report.n_skipped == 1
    assert any("blank.lrcat" in line for line in report.log)
    assert report.skipped[0]["reason"]


def test_learn_reports_icloud_placeholders(catalog_folder: Path, settings: Settings, tmp_path: Path):
    # A root holding an iCloud-evicted catalog placeholder (not openable).
    root = tmp_path / "icloudroot"
    root.mkdir()
    (root / ".Wedding.lrcat.icloud").write_bytes(b"")

    report = learn_from_folder([catalog_folder, root], "mix", settings, use_llm=False)
    assert report.n_catalogs == 1  # only the real downloaded catalog learned
    assert any("iCloud" in line for line in report.log)
    assert any("iCloud" in s["reason"] for s in report.skipped)


def test_learn_all_skipped_raises(settings: Settings, tmp_path: Path):
    from photovault.tests.make_fake import FakeImage, write_catalog

    root = tmp_path / "allblank"
    root.mkdir()
    write_catalog(
        root / "blank.lrcat",
        [FakeImage(base_name="x", capture_time="2024-01-01T00:00:00")],
    )
    with pytest.raises(ValueError):
        learn_from_folder(root, "x", settings, use_llm=False)


def test_learn_progress_events(catalog_folder: Path, settings: Settings):
    events: list = []
    learn_from_folder(catalog_folder, "p", settings, use_llm=False, progress=events.append)

    phases = [e["phase"] for e in events]
    assert "scan" in phases
    assert "save" in phases

    cat_events = [e for e in events if e["phase"] == "catalog"]
    assert len(cat_events) == 1
    ce = cat_events[0]
    assert ce["name"] == "shoot.lrcat"
    assert ce["index"] == 1 and ce["total"] == 1
    assert ce["kept"] is True
    # default_images() has 4-star keepers and an explicit reject flag.
    assert ce["stats"]["ratings"][4] >= 1
    assert ce["stats"]["n_images"] == 11


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
