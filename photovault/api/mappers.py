"""Pure mappers: backend artifacts -> the design's UI JSON shapes.

No FastAPI, no I/O beyond reading already-loaded objects. These are the main
TDD target (see ``test_api_mappers.py``); the FastAPI endpoints are thin wrappers
that call these and ``jsonable_encoder`` the result.

The target shapes are derived directly from ``design/pv-data.jsx``:

* ``profiles_list``  -> ``window.PROFILES`` (sidebar + inspector cards)
* ``profile_detail`` -> ``{meta, thresholds, presets, profileMd}`` (InspectorView)
* ``settings_view``  -> ``{cull, score, style, llm}`` (SettingsView)
* ``apply_payload``  -> ``{shoot, frames, bursts, bandCounts}``
  (window.SHOOT / ALL_SHOTS / BAND_COUNTS, ReviewView / ArbitrateView / ExportView)

Where the real ``Thresholds`` model lacks a UI field (e.g. the design shows full
aperture/ISO/focal *distributions* but we only persist min/median/mean/max
summary stats), we surface the real summary stats as labelled bars rather than
fabricating a fake distribution. Genuinely-absent fields fall back to sensible
empty/None values.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # avoid importing heavy/optional modules at import time
    from photovault.core.profile.store import LoadedProfile
    from photovault.core.score.pipeline import ApplyReport
    from photovault.settings import Settings

# Stable accent palette (mirrors the design's accent swatches).
_ACCENTS = [
    "#C98A3C",
    "#6E8BA8",
    "#9A938A",
    "#7FA882",
    "#B07CC6",
    "#D9756A",
    "#5FA8A0",
    "#C2A24B",
]

# Pull crs:* adjustment attrs out of a preset XMP packet (same regex family as
# core/export/xmp.py, kept local so mappers stay self-contained).
_CRS_ATTR = re.compile(r'crs:([A-Za-z0-9_]+)\s*=\s*"([^"]*)"')
_SKIP_CRS = {"Version", "PresetType", "ClusterGroup", "Name"}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def accent_for(name: str) -> str:
    """Deterministic accent color for a profile name (stable across calls)."""
    digest = hashlib.sha1(name.encode("utf-8")).digest()
    return _ACCENTS[digest[0] % len(_ACCENTS)]


def stars_for(score: float | None) -> int:
    """Map a 0..1 taste score to a 0..5 star rating (gate-only -> 0)."""
    if score is None:
        return 0
    return max(0, min(5, round(float(score) * 5)))


def _first_line(text: str | None) -> str:
    if not text:
        return ""
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped
    return ""


def _summary_bars(summary: dict[str, float]) -> list[dict[str, Any]]:
    """Turn a {min,median,mean,max} summary dict into labelled {k,v} bars.

    Honest surfacing of the real persisted stats: the design's full per-value
    distribution is NOT something M1-M4 persists, so we expose the four real
    summary statistics instead. ``v`` is sum-normalized into ``[0, 1]`` so it
    renders sensibly through the design's ``DistBar`` (which expects a fraction)
    without changing any component code. Empty dict -> empty list.
    """
    if not summary:
        return []
    order = ["min", "median", "mean", "max"]
    present = [(k, float(summary[k])) for k in order if k in summary]
    total = sum(abs(v) for _, v in present)
    if total <= 0:
        return [{"k": k, "v": 0.0} for k, _ in present]
    return [{"k": k, "v": round(abs(v) / total, 4)} for k, v in present]


# --------------------------------------------------------------------------- #
# profiles
# --------------------------------------------------------------------------- #
def profiles_list(settings: "Settings") -> list[dict[str, Any]]:
    """Build ``window.PROFILES`` from every profile under ``profiles_dir``."""
    from photovault.core.profile.store import PROFILE_LAYOUT, load_profile

    base = settings.profiles_dir.expanduser()
    if not base.exists():
        return []

    out: list[dict[str, Any]] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        if not (child / PROFILE_LAYOUT["meta"]).exists():
            continue
        try:
            prof = load_profile(settings.profiles_dir, child.name)
        except Exception:
            continue
        out.append(_profile_card(prof))
    return out


def _profile_card(prof: "LoadedProfile") -> dict[str, Any]:
    meta = prof.meta
    return {
        "id": prof.name,
        "name": prof.name,
        "en": prof.name,  # no separate english name persisted; reuse name
        "samples": meta.n_images,
        "catalogs": len(meta.source_catalogs),
        "keepRate": prof.thresholds.keep_rate,
        "built": meta.created_at.date().isoformat() if meta.created_at else "",
        "accent": accent_for(prof.name),
        "blurb": _first_line(prof.profile_md),
    }


def profile_detail(prof: "LoadedProfile") -> dict[str, Any]:
    """Build the InspectorView payload: meta + UI thresholds + presets + md."""
    return {
        "meta": prof.meta.model_dump(mode="json"),
        "thresholds": _thresholds_view(prof),
        "presets": _presets_view(prof),
        "profileMd": prof.profile_md or "",
    }


def _thresholds_view(prof: "LoadedProfile") -> dict[str, Any]:
    t = prof.thresholds
    # burst position bias: keep_position_mean in [0,1]; >0.5 -> late, <0.5 early.
    pos = t.keep_position_mean
    if pos > 0.55:
        bias = "late"
    elif pos < 0.45:
        bias = "early"
    else:
        bias = "even"
    iso_summary = t.iso or {}
    return {
        "keepRate": t.keep_rate,
        "keepRating": t.keep_rating,
        "rejectRating": t.reject_rating,
        # sharpness_floor is learned in the pixel stage; may be None on M1.
        "sharpnessFloor": t.sharpness_floor,
        # burst retain ~ avg keepers per burst frame (real persisted value).
        "burstRetain": round(t.burst_keep_rate, 3),
        "burstPosBias": bias,
        # ISO tolerance: the observed max keeper ISO if we have it, else None.
        "isoTolerance": int(iso_summary["max"]) if "max" in iso_summary else None,
        "burstGapSeconds": t.burst_gap_seconds,
        # Distributions: surfaced from the persisted summary stats as bars.
        "apertures": _summary_bars(t.aperture_f or {}),
        "focals": _summary_bars(t.focal_length or {}),
        "isoBuckets": _summary_bars(iso_summary),
    }


def _presets_view(prof: "LoadedProfile") -> list[dict[str, Any]]:
    presets: list[dict[str, Any]] = []
    for pf in prof.preset_files:
        try:
            xmp = pf.read_text(encoding="utf-8")
        except OSError:
            xmp = ""
        settings = {
            key: val
            for key, val in _CRS_ATTR.findall(xmp)
            if key not in _SKIP_CRS
        }
        presets.append(
            {
                "id": pf.stem,
                "name": pf.stem,
                "settings": settings,
                "sig": pf.stem == "signature",
            }
        )
    return presets


# --------------------------------------------------------------------------- #
# settings
# --------------------------------------------------------------------------- #
def settings_view(settings: "Settings") -> dict[str, Any]:
    """Build the SettingsView payload (cull / score / style / llm)."""
    return {
        "cull": settings.cull.model_dump(mode="json"),
        "score": settings.score.model_dump(mode="json"),
        "style": settings.style.model_dump(mode="json"),
        "llm": settings.llm.model_dump(mode="json"),
    }


# --------------------------------------------------------------------------- #
# apply result
# --------------------------------------------------------------------------- #
def thumb_url(path: str) -> str:
    """The /api/thumb URL the frontend uses to load a frame's pixels.

    Keyed by the photo's absolute path; the endpoint validates that the path is
    inside the last-applied folder before serving (path-traversal guard).
    """
    from urllib.parse import quote

    return "/api/thumb?path=" + quote(str(Path(path).resolve()))


def _frame(result: Any) -> dict[str, Any]:
    reasons = list(result.reasons or [])
    reason = " · ".join(reasons)
    low = reason.lower()
    return {
        "id": result.id,
        "burst": f"B{result.burst_id}",
        "src": thumb_url(result.path),
        "score": result.score,
        "band": result.decision,
        "stars": stars_for(result.score),
        # Pixel/EXIF fields the drawer reads; None when we don't compute them
        # in the API path (kept honest — the drawer tolerates nulls).
        "sharp": None,
        "iso": None,
        "ap": None,
        "focal": None,
        "sh": None,
        "preset": "",
        "reason": reason,
        "isDup": "near-duplicate" in low or "duplicate" in low or "dedup" in low,
        "blink": "blink" in low,
    }


def apply_payload(report: "ApplyReport", folder: str | Path) -> dict[str, Any]:
    """Build ``{shoot, frames, bursts, bandCounts}`` from an ApplyReport.

    Mirrors window.SHOOT / ALL_SHOTS / BAND_COUNTS in pv-data.jsx.
    """
    folder = Path(folder)
    frames = [_frame(r) for r in report.results]

    # Group frames into bursts (the design's SHOOT.bursts shape).
    bursts: dict[str, dict[str, Any]] = {}
    for f in frames:
        b = bursts.setdefault(
            f["burst"], {"id": f["burst"], "label": f["burst"], "shots": []}
        )
        b["shots"].append(f)
    burst_list = sorted(bursts.values(), key=lambda b: b["id"])

    return {
        "shoot": {
            "name": folder.name,
            "en": folder.name,
            "frames": len(frames),
        },
        "frames": frames,
        "bursts": burst_list,
        "bandCounts": {
            "keep": report.n_keep,
            "maybe": report.n_maybe,
            "reject": report.n_reject,
            "total": len(frames),
        },
    }
