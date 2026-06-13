from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pytest

PIL = pytest.importorskip("PIL")

from photovault.core.preview.extractor import (  # noqa: E402
    carve_largest_jpeg,
    extract_preview,
    find_preview,
)
from photovault.tests.make_images import (  # noqa: E402
    checkerboard,
    jpeg_bytes,
    wrap_lrprev,
    write_lrprev,
)


def _decode(data: bytes) -> np.ndarray:
    from PIL import Image

    return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))


def test_carve_roundtrip():
    arr = checkerboard(48, 4)
    jpeg = jpeg_bytes(arr)
    carved = carve_largest_jpeg(wrap_lrprev(jpeg))
    assert carved is not None
    # The carved JPEG decodes back to the same pixels.
    assert np.array_equal(_decode(carved), _decode(jpeg))


def test_carve_picks_largest():
    small = jpeg_bytes(checkerboard(16, 2))
    big = jpeg_bytes(checkerboard(64, 4))
    blob = b"xx" + small + b"yy" + big + b"zz"
    carved = carve_largest_jpeg(blob)
    assert carved == big


def test_carve_none_when_no_jpeg():
    assert carve_largest_jpeg(b"no markers here at all") is None


def test_extract_preview_lrprev(tmp_path: Path):
    arr = checkerboard(48, 4)
    p = write_lrprev(tmp_path / "x.lrprev", arr)
    data = extract_preview(p)
    assert data is not None
    assert np.array_equal(_decode(data), _decode(jpeg_bytes(arr)))


def test_extract_preview_missing(tmp_path: Path):
    assert extract_preview(tmp_path / "nope.lrprev") is None


def test_find_preview_by_basename(tmp_path: Path):
    cache = tmp_path / "previews"
    sub = cache / "ABC" / "deadbeef"
    sub.mkdir(parents=True)
    target = write_lrprev(sub / "deadbeef-7654.lrprev", checkerboard(32, 4))
    found = find_preview(cache, "deadbeef")
    assert found == target


def test_find_preview_none(tmp_path: Path):
    cache = tmp_path / "previews"
    cache.mkdir()
    assert find_preview(cache, "missing") is None
