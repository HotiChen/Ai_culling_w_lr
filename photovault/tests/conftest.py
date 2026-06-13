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


# --------------------------------------------------------------------------- #
# Stage-B (M3) fixtures: a learned profile + a new-photo folder.
# --------------------------------------------------------------------------- #
@pytest.fixture
def learned_profile(catalog_folder: Path, settings: Settings):
    """A full M2-style profile (taste_vector + classifier) learned with fakes.

    Runs the real stage-A pipeline against the synthetic catalog + a synthetic
    preview cache, using a FakeEmbedder so no model is ever downloaded. Returns
    the profile name; the profile lives under ``settings.profiles_dir``.
    """
    pytest.importorskip("PIL")
    from photovault.core.learn import learn_from_folder
    from photovault.tests.make_images import blobs, write_lrprev
    from photovault.tests.test_clip_embed import FakeEmbedder

    cache = settings.profiles_dir.parent / "previews.lrdata"
    for i, im in enumerate(default_images()):
        sub = cache / im.base_name[:1].upper() / im.base_name
        sub.mkdir(parents=True, exist_ok=True)
        write_lrprev(sub / f"{im.base_name}-9999.lrprev", blobs(seed=i))

    learn_from_folder(
        catalog_folder,
        "taste",
        settings,
        use_llm=False,
        preview_cache=cache,
        embedder=FakeEmbedder(),
    )
    return "taste"


@pytest.fixture
def new_photos(tmp_path: Path) -> Path:
    """A folder of fresh JPEGs: a 4-frame burst + two singles, with capture EXIF.

    Burst frames are shot ~1s apart (one tight burst under the default 2s gap);
    the two singles are minutes apart so they stay singletons.
    """
    pytest.importorskip("PIL")
    from photovault.tests.make_images import blobs, write_jpeg_with_capture_time

    folder = tmp_path / "new_photos"
    folder.mkdir()
    # A tight burst of 4 near-duplicate frames (same blob seed family).
    for k in range(4):
        write_jpeg_with_capture_time(
            folder / f"burst_{k}.jpg",
            blobs(seed=100 + k),
            f"2024:03:01 09:00:0{k}",
            ISOSpeedRatings=400,
            FNumber=2.0,
            FocalLength=85.0,
        )
    # Two singles, far apart in time.
    write_jpeg_with_capture_time(
        folder / "single_a.jpg",
        blobs(seed=7),
        "2024:03:01 10:00:00",
        ISOSpeedRatings=200,
        FNumber=1.4,
        FocalLength=85.0,
    )
    write_jpeg_with_capture_time(
        folder / "single_b.jpg",
        blobs(seed=9),
        "2024:03:01 11:00:00",
        ISOSpeedRatings=100,
        FNumber=4.0,
        FocalLength=35.0,
    )
    return folder
