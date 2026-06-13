"""Self-contained HTML review report (M3).

Pure string assembly — no template framework, no external CSS/JS. One row per
image with its filename, score, decision and gate/dedup reasons, plus a header
summarizing the bucket counts. Thumbnails are embedded as base64 data URIs when
Pillow is available; otherwise rows render text-only so the report still works
with zero optional deps.
"""

from __future__ import annotations

import base64
import io
from collections import Counter
from html import escape
from pathlib import Path
from typing import Sequence

from photovault.core.score.engine import KEEP, MAYBE, REJECT, ScoreResult

# Decision -> a soft background color so buckets are scannable at a glance.
_COLORS = {KEEP: "#e6f4ea", MAYBE: "#fef7e0", REJECT: "#fce8e6"}

_STYLE = """
body { font-family: -apple-system, system-ui, sans-serif; margin: 2rem; color: #202124; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #dadce0; padding: 6px 10px; text-align: left; vertical-align: top; }
th { background: #f1f3f4; }
img.thumb { max-width: 120px; max-height: 90px; display: block; }
.summary span { display: inline-block; margin-right: 1.5rem; font-weight: 600; }
""".strip()


def _thumb_data_uri(path: str, max_side: int = 160) -> str | None:
    """Return a base64 PNG data URI for *path*, or ``None`` if it can't load."""
    try:
        from PIL import Image  # lazy: thumbnails are optional
    except ImportError:
        return None
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
    except Exception:
        return None
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _fmt_score(score: float | None) -> str:
    return "—" if score is None else f"{score:.2f}"


def render_report(results: Sequence[ScoreResult], embed_thumbs: bool = True) -> str:
    """Render the review report as an HTML string."""
    counts = Counter(r.decision for r in results)
    summary = " ".join(
        f'<span style="background:{_COLORS.get(d, "#fff")}">{d}: {counts.get(d, 0)}</span>'
        for d in (KEEP, MAYBE, REJECT)
    )

    rows = []
    for r in results:
        thumb_cell = ""
        if embed_thumbs:
            uri = _thumb_data_uri(r.path)
            if uri:
                thumb_cell = f'<img class="thumb" src="{uri}" alt="{escape(r.id)}">'
        reasons = "; ".join(escape(x) for x in r.reasons)
        rows.append(
            f'    <tr style="background:{_COLORS.get(r.decision, "#fff")}">\n'
            f"      <td>{thumb_cell}</td>\n"
            f"      <td>{escape(r.id)}</td>\n"
            f"      <td>{escape(Path(r.path).name)}</td>\n"
            f"      <td>{_fmt_score(r.score)}</td>\n"
            f"      <td>{escape(r.decision)}</td>\n"
            f"      <td>{reasons}</td>\n"
            "    </tr>"
        )
    rows_html = "\n".join(rows)

    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        "<title>PhotoVault review</title>\n"
        f"<style>{_STYLE}</style>\n</head>\n<body>\n"
        "<h1>PhotoVault review</h1>\n"
        f'<p class="summary">{summary}</p>\n'
        "<table>\n  <thead>\n    <tr>"
        "<th>Preview</th><th>ID</th><th>File</th>"
        "<th>Score</th><th>Decision</th><th>Reasons</th></tr>\n"
        "  </thead>\n  <tbody>\n"
        f"{rows_html}\n"
        "  </tbody>\n</table>\n</body>\n</html>\n"
    )


def write_report(
    results: Sequence[ScoreResult], out_path: str | Path, embed_thumbs: bool = True
) -> Path:
    """Write the HTML report to *out_path* and return it."""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(results, embed_thumbs=embed_thumbs), encoding="utf-8")
    return out
