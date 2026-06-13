from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from photovault.core.catalog.reader import ExifData  # noqa: E402
from photovault.core.features.exif import read_exif  # noqa: E402
from photovault.tests.make_images import checkerboard, write_jpeg  # noqa: E402


def test_read_exif_from_jpeg(tmp_path: Path):
    from PIL.ExifTags import Base

    exif = {
        Base.FNumber.value: (28, 10),          # f/2.8
        Base.ExposureTime.value: (1, 250),     # 1/250 s
        Base.ISOSpeedRatings.value: 200,
        Base.FocalLength.value: (50, 1),       # 50 mm
    }
    path = write_jpeg(tmp_path / "shot.jpg", checkerboard(32, 4), exif=exif)

    data = read_exif(path)
    assert isinstance(data, ExifData)
    assert data.aperture_f == pytest.approx(2.8, abs=0.01)
    assert data.shutter_seconds == pytest.approx(1 / 250, rel=0.01)
    assert data.iso == 200
    assert data.focal_length == pytest.approx(50.0)


def test_read_exif_no_metadata(tmp_path: Path):
    path = write_jpeg(tmp_path / "plain.jpg", checkerboard(32, 4))
    data = read_exif(path)
    assert isinstance(data, ExifData)
    assert data.aperture_f is None
    assert data.iso is None
