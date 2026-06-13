from __future__ import annotations

from pathlib import Path

import pytest

from photovault.core.catalog.style import Preset
from photovault.core.profile.models import ProfileMeta, Thresholds
from photovault.core.profile.store import (
    load_profile,
    profile_exists,
    save_profile,
)


def _make(tmp_path: Path, name="熱茶"):
    meta = ProfileMeta(name=name, n_images=11, n_keepers=6, n_rejects=4, n_presets=2,
                       source_catalogs=["/x/shoot.lrcat"])
    thresholds = Thresholds(keep_rate=0.6, aperture_f={"median": 1.8},
                            keep_position_mean=0.85)
    presets = [
        Preset(name="look_1", params={"Exposure2012": 0.35, "Temperature": 5600}, support=4),
        Preset(name="look_2", params={"Contrast2012": 35}, support=2),
    ]
    signature = Preset(name="signature", params={"Exposure2012": 0.1}, support=6)
    return meta, thresholds, presets, signature


def test_save_and_load_roundtrip(tmp_path: Path):
    profiles_dir = tmp_path / "profiles"
    meta, thresholds, presets, signature = _make(tmp_path)

    assert not profile_exists(profiles_dir, "熱茶")
    base = save_profile(profiles_dir, "熱茶", meta, thresholds, presets, signature)
    assert profile_exists(profiles_dir, "熱茶")

    # Files on disk match the documented layout.
    assert (base / "meta.json").exists()
    assert (base / "thresholds.json").exists()
    assert (base / "profile.md").exists()
    assert (base / "presets" / "look_1.xmp").exists()
    assert (base / "presets" / "signature.xmp").exists()

    loaded = load_profile(profiles_dir, "熱茶")
    assert loaded.meta.name == "熱茶"
    assert loaded.meta.n_keepers == 6
    assert loaded.thresholds.keep_rate == 0.6
    assert loaded.thresholds.keep_position_mean == 0.85
    assert {p.stem for p in loaded.preset_files} == {"look_1", "look_2", "signature"}
    assert "熱茶" in (loaded.profile_md or "")


def test_load_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_profile(tmp_path / "profiles", "ghost")


def test_overwrite_replaces(tmp_path: Path):
    profiles_dir = tmp_path / "profiles"
    meta, thresholds, presets, signature = _make(tmp_path)
    save_profile(profiles_dir, "p", meta, thresholds, presets, signature)
    # Save again with a single preset -> stale look_2.xmp must be gone.
    save_profile(profiles_dir, "p", meta, thresholds, presets[:1], signature)
    loaded = load_profile(profiles_dir, "p")
    assert {p.stem for p in loaded.preset_files} == {"look_1", "signature"}
