from __future__ import annotations

import csv
from pathlib import Path

from photovault.core.catalog.labels import (
    FIELDNAMES,
    build_rows,
    labeled_only,
    write_csv,
)
from photovault.core.catalog.reader import iter_images, open_ro
from photovault.settings import CullSettings


def _load(catalog_path):
    conn = open_ro(catalog_path)
    imgs = list(iter_images(conn))
    conn.close()
    return imgs


def test_build_rows(catalog_path):
    rows = build_rows(_load(catalog_path), CullSettings())
    assert len(rows) == 11

    by_name = {r.filename: r for r in rows}
    # burst frames carry burst context
    b0 = by_name["burst_0.dng"]
    assert b0.burst_size == 5
    assert b0.burst_position == 0.0
    assert b0.label == "reject"
    b4 = by_name["burst_4.dng"]
    assert b4.burst_position == 1.0
    assert b4.label == "keep"
    # singletons have no position
    assert by_name["portrait_a.dng"].burst_size == 1
    assert by_name["portrait_a.dng"].burst_position is None


def test_labeled_only(catalog_path):
    rows = build_rows(_load(catalog_path), CullSettings())
    trainable = labeled_only(rows)
    assert all(r.label in ("keep", "reject") for r in trainable)
    assert len(trainable) == 10  # 11 - 1 unlabeled


def test_write_csv(catalog_path, tmp_path: Path):
    rows = build_rows(_load(catalog_path), CullSettings())
    out = write_csv(rows, tmp_path / "sub" / "labels.csv")
    assert out.exists()

    with out.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == FIELDNAMES
        loaded = list(reader)
    assert len(loaded) == 11
    assert loaded[0]["filename"] == "burst_0.dng"
