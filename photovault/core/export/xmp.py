"""XMP sidecar writer (M3): rating + pick/reject flag + best develop preset.

We emit a small, well-formed XMP packet next to each photo (``photo.xmp``) using
the ``crs:`` (Camera Raw) and ``xmp:`` namespaces Lightroom understands:

* ``xmp:Rating`` — star rating derived from the decision.
* ``crs:Pick`` flag — ``1`` keep / ``-1`` reject / ``0`` undecided.
* the matched develop preset's ``crs:*`` adjustment attributes (optional).

Writing is idempotent: the same :class:`ScoreResult` + preset always yields
byte-identical output (overwrite, no timestamps).
"""

from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import quoteattr

from photovault.core.score.engine import KEEP, MAYBE, REJECT, ScoreResult

# Star ratings per decision. A keeper is a 4-star pick, the gray zone a neutral
# 2 stars (so it is easy to find for review), a reject a flagged-out 0.
_RATING = {KEEP: 4, MAYBE: 2, REJECT: 0}
_PICK = {KEEP: 1, MAYBE: 0, REJECT: -1}

# Pull crs:* adjustment attributes out of a preset XMP packet so we can re-embed
# them in the per-photo sidecar (the preset's own wrapper is discarded).
_CRS_ATTR = re.compile(r'crs:([A-Za-z0-9_]+)\s*=\s*"([^"]*)"')

# Develop-only crs keys we never copy from a preset (they are sidecar metadata,
# not look adjustments).
_SKIP_CRS = {"Version", "PresetType", "ClusterGroup", "Name"}


def rating_for(decision: str) -> int:
    """Star rating (0..5) for a decision."""
    return _RATING.get(decision, 2)


def _pick_for(decision: str) -> int:
    return _PICK.get(decision, 0)


def _preset_crs_attrs(preset_xmp: str | None) -> list[tuple[str, str]]:
    """Extract ``(key, value)`` develop adjustments from a preset XMP string."""
    if not preset_xmp:
        return []
    return [
        (key, val)
        for key, val in _CRS_ATTR.findall(preset_xmp)
        if key not in _SKIP_CRS
    ]


def build_sidecar_xmp(result: ScoreResult, preset_xmp: str | None = None) -> str:
    """Build the XMP sidecar packet for *result* (pure string, no I/O)."""
    rating = rating_for(result.decision)
    pick = _pick_for(result.decision)

    crs_lines = [
        f'    crs:Version="15.0"',
        f'    crs:Pick={quoteattr(str(pick))}',
    ]
    for key, val in _preset_crs_attrs(preset_xmp):
        crs_lines.append(f"    crs:{key}={quoteattr(val)}")
    crs_block = "\n".join(crs_lines)

    label = result.decision  # human-readable bucket as the XMP label
    return (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="PhotoVault">\n'
        ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '  <rdf:Description rdf:about=""\n'
        '    xmlns:xmp="http://ns.adobe.com/xap/1.0/"\n'
        '    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"\n'
        f'    xmp:Rating={quoteattr(str(rating))}\n'
        f'    xmp:Label={quoteattr(label)}\n'
        f"{crs_block}>\n"
        "  </rdf:Description>\n"
        " </rdf:RDF>\n"
        "</x:xmpmeta>\n"
    )


def write_sidecar(
    result: ScoreResult, preset_xmp: str | None = None
) -> Path:
    """Write ``<photo>.xmp`` next to the photo and return its path (idempotent)."""
    out = Path(result.path).with_suffix(".xmp")
    out.write_text(build_sidecar_xmp(result, preset_xmp), encoding="utf-8")
    return out
