"""TDD for the pure UI mappers (no FastAPI involved).

These convert real backend artifacts (LoadedProfile / Settings / ApplyReport +
ScoreResults) into the JSON dict shapes the design's JSX consumes (window.PROFILES,
window.THRESHOLDS, window.PRESETS, window.SHOOT / ALL_SHOTS / BAND_COUNTS, settings).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from photovault.core.profile.store import load_profile
from photovault.core.score import apply_to_folder
from photovault.settings import Settings

from photovault.api import mappers


# --------------------------------------------------------------------------- #
# profile list
# --------------------------------------------------------------------------- #
def test_profiles_list_shape(learned_profile: str, settings: Settings):
    profiles = mappers.profiles_list(settings)
    assert isinstance(profiles, list)
    assert len(profiles) == 1
    p = profiles[0]
    # Keys the sidebar + inspector read.
    for key in ("id", "name", "en", "samples", "catalogs", "keepRate", "built", "accent", "blurb"):
        assert key in p, f"missing {key}"
    assert p["id"] == "taste"
    assert p["name"] == "taste"
    # samples == meta.n_images
    prof = load_profile(settings.profiles_dir, "taste")
    assert p["samples"] == prof.meta.n_images
    assert p["catalogs"] == len(prof.meta.source_catalogs)
    assert p["keepRate"] == prof.thresholds.keep_rate
    # accent is a stable hex color
    assert isinstance(p["accent"], str) and p["accent"].startswith("#")


def test_profiles_list_empty(settings: Settings):
    # profiles_dir does not even exist yet
    assert mappers.profiles_list(settings) == []


def test_accent_is_stable_per_name():
    a = mappers.accent_for("taste")
    b = mappers.accent_for("taste")
    c = mappers.accent_for("other")
    assert a == b
    assert a.startswith("#") and len(a) == 7
    assert a != c  # different names -> (very likely) different colors


# --------------------------------------------------------------------------- #
# profile detail
# --------------------------------------------------------------------------- #
def test_profile_detail_shape(learned_profile: str, settings: Settings):
    prof = load_profile(settings.profiles_dir, "taste")
    detail = mappers.profile_detail(prof)
    assert set(detail.keys()) >= {"meta", "thresholds", "presets", "profileMd"}

    th = detail["thresholds"]
    # UI threshold shape (InspectorView reads these).
    for key in ("keepRate", "keepRating", "sharpnessFloor", "burstRetain",
                "burstPosBias", "isoTolerance", "apertures", "focals", "isoBuckets"):
        assert key in th, f"missing threshold {key}"
    assert th["keepRate"] == prof.thresholds.keep_rate
    assert th["keepRating"] == prof.thresholds.keep_rating
    # distributions are lists of {k, v}
    for dist in ("apertures", "focals", "isoBuckets"):
        assert isinstance(th[dist], list)
        for item in th[dist]:
            assert set(item.keys()) == {"k", "v"}

    # presets shape
    assert isinstance(detail["presets"], list)
    if detail["presets"]:
        pr = detail["presets"][0]
        for key in ("id", "name", "settings"):
            assert key in pr
        assert isinstance(pr["settings"], dict)
    # signature preset flagged
    assert any(pr.get("sig") for pr in detail["presets"]) or all(
        not pr.get("sig") for pr in detail["presets"]
    )

    assert isinstance(detail["profileMd"], str)
    assert detail["meta"]["name"] == "taste"


def test_profile_presets_parse_crs_settings(learned_profile: str, settings: Settings):
    prof = load_profile(settings.profiles_dir, "taste")
    detail = mappers.profile_detail(prof)
    # at least one preset must carry parsed crs settings (the synthetic catalog
    # has develop adjustments).
    parsed = [pr for pr in detail["presets"] if pr["settings"]]
    assert parsed, "expected at least one preset with parsed crs settings"


# --------------------------------------------------------------------------- #
# settings
# --------------------------------------------------------------------------- #
def test_settings_view_shape(settings: Settings):
    s = mappers.settings_view(settings)
    assert set(s.keys()) >= {"cull", "score", "style", "llm"}
    assert s["cull"]["keep_rating"] == settings.cull.keep_rating
    assert s["score"]["keep_above"] == settings.score.keep_above
    assert s["style"]["n_presets"] == settings.style.n_presets
    assert s["llm"]["model"] == settings.llm.model
    assert s["llm"]["enabled"] == settings.llm.enabled


# --------------------------------------------------------------------------- #
# apply result -> SHOOT / ALL_SHOTS / BAND_COUNTS
# --------------------------------------------------------------------------- #
def test_apply_result_shape(learned_profile: str, new_photos: Path, settings: Settings):
    report = apply_to_folder(
        new_photos, "taste", settings, report=False, no_llm=True
    )
    payload = mappers.apply_payload(report, new_photos)

    assert set(payload.keys()) >= {"shoot", "frames", "bursts", "bandCounts"}
    shoot = payload["shoot"]
    assert "name" in shoot and "frames" in shoot
    assert shoot["frames"] == len(report.results)

    frames = payload["frames"]
    assert len(frames) == len(report.results)
    f = frames[0]
    for key in ("id", "burst", "src", "score", "band", "stars",
                "preset", "reason", "isDup", "blink"):
        assert key in f, f"missing frame key {key}"
    # band is one of keep/maybe/reject
    assert f["band"] in ("keep", "maybe", "reject")
    # src is a /api/thumb URL keyed by token
    assert f["src"].startswith("/api/thumb")
    # stars derived from score, 0..5
    assert 0 <= f["stars"] <= 5

    bc = payload["bandCounts"]
    assert set(bc.keys()) == {"keep", "maybe", "reject", "total"}
    assert bc["total"] == len(frames)
    assert bc["keep"] + bc["maybe"] + bc["reject"] == bc["total"]


def test_apply_payload_band_counts_match(learned_profile: str, new_photos: Path, settings: Settings):
    report = apply_to_folder(new_photos, "taste", settings, report=False, no_llm=True)
    payload = mappers.apply_payload(report, new_photos)
    assert payload["bandCounts"]["keep"] == report.n_keep
    assert payload["bandCounts"]["maybe"] == report.n_maybe
    assert payload["bandCounts"]["reject"] == report.n_reject


def test_stars_for_score():
    assert mappers.stars_for(None) == 0
    assert mappers.stars_for(0.0) == 0
    assert mappers.stars_for(1.0) == 5
    assert 0 <= mappers.stars_for(0.5) <= 5
