"""CSV export of stage-B cull decisions.

One row per scored photo: filename, decision band, star rating, taste score,
burst id and the joined reasons. A plain, spreadsheet-friendly summary of what
the cull did — the companion to the HTML review report.
"""

from __future__ import annotations

import csv
from pathlib import Path

from photovault.core.export.xmp import rating_for
from photovault.core.score.engine import ScoreResult

FIELDNAMES = ["filename", "decision", "stars", "score", "burst", "reasons", "path"]


def write_decisions_csv(results: list[ScoreResult], path: str | Path) -> Path:
    """Write *results* to a CSV at *path* (creating parents). Returns the path."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as fh:  # BOM for Excel
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for r in results:
            writer.writerow(
                {
                    "filename": Path(r.path).name,
                    "decision": r.decision,
                    "stars": rating_for(r.decision),
                    "score": "" if r.score is None else round(float(r.score), 4),
                    "burst": r.burst_id,
                    "reasons": " · ".join(r.reasons or []),
                    "path": r.path,
                }
            )
    return out
