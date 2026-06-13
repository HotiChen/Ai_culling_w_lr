from __future__ import annotations

from pathlib import Path

import pytest

from photovault.core.catalog import reader
from photovault.core.catalog.reader import (
    apex_to_fnumber,
    apex_to_shutter_seconds,
    find_catalogs,
    iter_images,
    open_ro,
    parse_develop_text,
    table_columns,
    table_exists,
)


def test_find_catalogs(catalog_folder: Path):
    found = find_catalogs(catalog_folder)
    assert len(found) == 1
    assert found[0].name == "shoot.lrcat"


def test_find_catalogs_missing_folder(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        find_catalogs(tmp_path / "nope")


def test_open_ro_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        open_ro(tmp_path / "missing.lrcat")


def test_open_ro_is_readonly(catalog_path: Path):
    conn = open_ro(catalog_path)
    with pytest.raises(Exception):
        conn.execute("CREATE TABLE hack (x)")
    conn.close()


def test_schema_introspection(catalog_path: Path):
    conn = open_ro(catalog_path)
    assert table_exists(conn, "Adobe_images")
    assert not table_exists(conn, "DoesNotExist")
    cols = table_columns(conn, "Adobe_images")
    assert "captureTime" in cols and "rating" in cols
    assert table_columns(conn, "DoesNotExist") == []
    conn.close()


def test_iter_images_count_and_join(catalog_path: Path):
    conn = open_ro(catalog_path)
    images = list(iter_images(conn))
    conn.close()
    assert len(images) == 11  # 5 burst + 2 portrait + 2 scape + 1 misc + 1 reject

    by_name = {im.base_name: im for im in images}
    p = by_name["portrait_a"]
    assert p.rating == 5
    assert p.pick == 1
    assert p.extension == "dng"
    assert p.filename == "portrait_a.dng"


def test_exif_apex_conversion(catalog_path: Path):
    conn = open_ro(catalog_path)
    by_name = {im.base_name: im for im in iter_images(conn)}
    conn.close()
    # portrait_a was stored at f/1.4
    assert by_name["portrait_a"].exif.aperture_f == pytest.approx(1.4, abs=0.05)
    # scape_a at f/4
    assert by_name["scape_a"].exif.aperture_f == pytest.approx(4.0, abs=0.05)
    assert by_name["portrait_a"].exif.iso == 200
    assert by_name["portrait_a"].exif.focal_length == pytest.approx(85.0)


def test_develop_parsed(catalog_path: Path):
    conn = open_ro(catalog_path)
    by_name = {im.base_name: im for im in iter_images(conn)}
    conn.close()
    warm = by_name["portrait_a"].develop
    assert warm.has_adjustments
    assert warm.params["Temperature"] == pytest.approx(5600)
    assert warm.params["Exposure2012"] == pytest.approx(0.35)
    # misc_single had no edits
    assert by_name["misc_single"].develop.params == {}


def test_apex_helpers_none():
    assert apex_to_fnumber(None) is None
    assert apex_to_shutter_seconds(None) is None
    assert apex_to_fnumber(2.0) == pytest.approx(2.0, abs=0.01)


def test_parse_develop_text_tolerant():
    assert parse_develop_text(None) == {}
    assert parse_develop_text("") == {}
    parsed = parse_develop_text('s = { Exposure2012 = 0.5, Name = "x", Flag = true }')
    assert parsed == {"Exposure2012": 0.5}


def test_not_a_catalog(tmp_path: Path):
    import sqlite3

    bad = tmp_path / "bad.lrcat"
    sqlite3.connect(bad).close()
    conn = open_ro(bad)
    with pytest.raises(ValueError):
        list(iter_images(conn))
    conn.close()
