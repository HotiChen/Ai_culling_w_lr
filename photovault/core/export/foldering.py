"""Optional foldering (M3): copy photos into keep/maybe/reject subfolders.

We **copy** (or symlink) — never move — so the user's originals are never
touched. This is off by default in the pipeline; the CLI exposes it behind
``--sort``. Idempotent: re-running overwrites the copies rather than failing.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Sequence

from photovault.core.score.engine import ScoreResult


def sort_into_folders(
    results: Sequence[ScoreResult],
    dest: str | Path,
    symlink: bool = False,
) -> dict[str, list[Path]]:
    """Copy each photo into ``dest/<decision>/`` and return the new paths.

    With *symlink* true we link instead of copying (still non-destructive). The
    returned mapping is ``{decision: [new_path, ...]}`` for the buckets used.
    """
    base = Path(dest)
    out: dict[str, list[Path]] = {}
    for r in results:
        src = Path(r.path)
        if not src.exists():
            continue
        bucket = base / r.decision
        bucket.mkdir(parents=True, exist_ok=True)
        target = bucket / src.name
        _place(src, target, symlink=symlink)
        out.setdefault(r.decision, []).append(target)
    return out


def _place(src: Path, target: Path, symlink: bool) -> None:
    """Put a non-destructive copy/symlink of *src* at *target* (overwrite)."""
    if target.exists() or target.is_symlink():
        target.unlink()
    if symlink:
        os.symlink(src.resolve(), target)
    else:
        shutil.copy2(src, target)
