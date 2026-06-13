"""M2: the optional pixel stage of the stage-A learning pipeline."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("PIL")

from photovault.core.learn import learn_from_folder  # noqa: E402
from photovault.core.profile import load_profile  # noqa: E402
from photovault.settings import Settings  # noqa: E402
from photovault.tests.make_fake import default_images, write_catalog  # noqa: E402
from photovault.tests.make_images import blobs, write_lrprev  # noqa: E402
from photovault.tests.test_clip_embed import FakeEmbedder  # noqa: E402


@pytest.fixture
def preview_cache(tmp_path: Path) -> Path:
    """A preview cache holding one .lrprev per default catalog image (by base name)."""
    cache = tmp_path / "previews.lrdata"
    for i, im in enumerate(default_images()):
        sub = cache / im.base_name[:1].upper() / im.base_name
        sub.mkdir(parents=True, exist_ok=True)
        write_lrprev(sub / f"{im.base_name}-9999.lrprev", blobs(seed=i))
    return cache


def test_pixel_stage_populates_taste_and_classifier(
    catalog_folder: Path, settings: Settings, preview_cache: Path
):
    report = learn_from_folder(
        catalog_folder,
        "pix",
        settings,
        use_llm=False,
        preview_cache=preview_cache,
        embedder=FakeEmbedder(),
    )
    assert report.pixels_used is True
    assert report.n_embedded > 0

    prof = load_profile(settings.profiles_dir, "pix")
    assert prof.taste_vector is not None
    assert np.linalg.norm(prof.taste_vector) == pytest.approx(1.0, abs=1e-5)
    assert prof.classifier is not None
    assert (prof.path / "chroma").is_dir()


def test_pixel_stage_skipped_without_embedder(
    catalog_folder: Path, settings: Settings, preview_cache: Path
):
    # No embedder available and none constructible -> gracefully skip, M1 still works.
    report = learn_from_folder(
        catalog_folder,
        "nopix",
        settings,
        use_llm=False,
        preview_cache=preview_cache,
        embedder=None,
    )
    assert report.pixels_used is False
    assert "embedder" in report.pixels_note.lower() or report.pixels_note != ""

    prof = load_profile(settings.profiles_dir, "nopix")
    assert prof.taste_vector is None


def test_pixel_stage_skipped_without_cache(catalog_folder: Path, settings: Settings):
    report = learn_from_folder(
        catalog_folder, "nocache", settings, use_llm=False, embedder=FakeEmbedder()
    )
    assert report.pixels_used is False
