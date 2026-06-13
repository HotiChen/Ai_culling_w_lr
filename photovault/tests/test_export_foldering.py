"""M3: optional sorting of photos into keep/maybe/reject subfolders (copy, never move)."""

from __future__ import annotations

from pathlib import Path

from photovault.core.export.foldering import sort_into_folders
from photovault.core.score.engine import ScoreResult


def _photo(tmp_path: Path, name: str) -> str:
    p = tmp_path / name
    p.write_bytes(b"data-" + name.encode())
    return str(p)


def _res(path: str, decision: str) -> ScoreResult:
    return ScoreResult(
        id=Path(path).stem,
        path=path,
        score=0.5,
        decision=decision,
        reasons=[],
        burst_id=0,
        embedding=None,
    )


def test_sort_copies_into_decision_folders(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "out"
    results = [
        _res(_photo(src, "k.jpg"), "keep"),
        _res(_photo(src, "m.jpg"), "maybe"),
        _res(_photo(src, "r.jpg"), "reject"),
    ]
    paths = sort_into_folders(results, dst)
    assert (dst / "keep" / "k.jpg").exists()
    assert (dst / "maybe" / "m.jpg").exists()
    assert (dst / "reject" / "r.jpg").exists()
    # Returned mapping points at the new copies.
    assert set(paths.keys()) == {"keep", "maybe", "reject"}


def test_sort_never_destroys_originals(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "out"
    p = _photo(src, "orig.jpg")
    sort_into_folders([_res(p, "keep")], dst)
    # Original must survive (we copy, never move).
    assert Path(p).exists()
    assert (dst / "keep" / "orig.jpg").read_bytes() == Path(p).read_bytes()


def test_sort_is_idempotent(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    dst = tmp_path / "out"
    res = [_res(_photo(src, "a.jpg"), "keep")]
    sort_into_folders(res, dst)
    sort_into_folders(res, dst)  # second run must not raise
    assert (dst / "keep" / "a.jpg").exists()
