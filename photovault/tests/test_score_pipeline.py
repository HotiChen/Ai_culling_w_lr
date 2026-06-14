"""M3: stage-B orchestration — apply_to_folder end to end with fakes."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PIL")

from photovault.core.score.pipeline import ApplyReport, apply_to_folder  # noqa: E402
from photovault.settings import Settings  # noqa: E402
from photovault.tests.test_clip_embed import FakeEmbedder  # noqa: E402


def _fake_blink(_arr):
    """No mediapipe in tests — pretend nothing blinked."""
    return None


def test_apply_produces_decisions_and_outputs(
    new_photos: Path, settings: Settings, learned_profile: str
):
    report = apply_to_folder(
        new_photos,
        learned_profile,
        settings,
        embedder=FakeEmbedder(),
        blink_fn=_fake_blink,
    )
    assert isinstance(report, ApplyReport)
    # Every input image is accounted for in exactly one bucket.
    assert report.n_keep + report.n_maybe + report.n_reject == report.n_images
    assert report.n_images == 6  # 4 burst + 2 singles
    # XMP sidecars written next to every photo.
    for p in new_photos.glob("*.jpg"):
        assert p.with_suffix(".xmp").exists()
    # HTML report written.
    assert report.report_path is not None
    assert Path(report.report_path).exists()


def test_apply_emits_per_photo_progress(
    new_photos: Path, settings: Settings, learned_profile: str
):
    events: list = []
    apply_to_folder(
        new_photos, learned_profile, settings,
        embedder=FakeEmbedder(), blink_fn=_fake_blink, progress=events.append,
    )
    phases = [e["phase"] for e in events]
    assert "scan" in phases and "export" in phases
    photos = [e for e in events if e["phase"] == "photo"]
    assert len(photos) == 6  # one event per image
    for ph in photos:
        assert ph["name"].endswith(".jpg")
        assert ph["band"] in ("keep", "maybe", "reject")
        assert 0 <= ph["stars"] <= 5


def test_apply_dedups_the_burst(
    new_photos: Path, settings: Settings, learned_profile: str
):
    # Tighten dedup so the 4 near-duplicate burst frames collapse hard.
    settings.score.phash_hamming_max = 64
    report = apply_to_folder(
        new_photos,
        learned_profile,
        settings,
        embedder=FakeEmbedder(),
        blink_fn=_fake_blink,
    )
    # With a 4-frame burst, dedup must reject at least one near-duplicate.
    assert report.n_reject >= 1


def test_apply_gate_only_for_m1_profile(
    new_photos: Path, settings: Settings, catalog_folder: Path
):
    """A profile lacking taste_vector/classifier degrades to gate-only + a note."""
    from photovault.core.learn import learn_from_folder

    learn_from_folder(catalog_folder, "m1only", settings, use_llm=False)
    report = apply_to_folder(
        new_photos, "m1only", settings, embedder=FakeEmbedder(), blink_fn=_fake_blink
    )
    assert report.n_images == 6
    assert "gate" in " ".join(report.notes).lower()


def test_apply_without_embedder_skips_taste(
    new_photos: Path, settings: Settings, learned_profile: str
):
    report = apply_to_folder(
        new_photos, learned_profile, settings, embedder=None, blink_fn=_fake_blink
    )
    # Should not crash; taste-similarity term skipped with a note.
    assert report.n_images == 6
    assert any("embed" in n.lower() or "taste" in n.lower() for n in report.notes)


def test_apply_optional_foldering(
    new_photos: Path, settings: Settings, learned_profile: str, tmp_path: Path
):
    out = tmp_path / "sorted"
    report = apply_to_folder(
        new_photos,
        learned_profile,
        settings,
        embedder=FakeEmbedder(),
        blink_fn=_fake_blink,
        sort_dir=out,
    )
    assert out.exists()
    # At least one decision folder was created and originals are intact.
    assert any(out.iterdir())
    for p in new_photos.glob("*.jpg"):
        assert p.exists()
    assert report.sorted_dir == out
