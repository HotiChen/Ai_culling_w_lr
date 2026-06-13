"""M3: XMP sidecar export — rating + pick/reject flag + preset, parseable XML."""

from __future__ import annotations

from pathlib import Path
from xml.dom import minidom

from photovault.core.export.xmp import rating_for, write_sidecar
from photovault.core.score.engine import ScoreResult


def _res(decision: str, path: str, score: float = 0.7) -> ScoreResult:
    return ScoreResult(
        id=Path(path).stem,
        path=path,
        score=score,
        decision=decision,
        reasons=[],
        burst_id=0,
        embedding=None,
    )


def test_rating_for_maps_decisions():
    assert rating_for("keep") >= 3
    assert rating_for("reject") == 0
    assert 0 < rating_for("maybe") < rating_for("keep")


def test_write_sidecar_is_parseable_and_next_to_photo(tmp_path: Path):
    photo = tmp_path / "shot.jpg"
    photo.write_bytes(b"\xff\xd8\xff\xd9")  # not a real JPEG, just a placeholder
    out = write_sidecar(_res("keep", str(photo)), preset_xmp=None)
    assert out == photo.with_suffix(".xmp")
    assert out.exists()
    # Must be well-formed XML.
    doc = minidom.parseString(out.read_text(encoding="utf-8"))
    assert doc.documentElement is not None


def test_sidecar_encodes_rating_and_pick(tmp_path: Path):
    photo = tmp_path / "keep.jpg"
    photo.write_bytes(b"x")
    out = write_sidecar(_res("keep", str(photo)), preset_xmp=None)
    text = out.read_text(encoding="utf-8")
    assert "Rating" in text
    # A keeper is flagged as a pick.
    assert "Pick" in text or "pick" in text.lower()


def test_reject_sidecar_flags_reject(tmp_path: Path):
    photo = tmp_path / "bad.jpg"
    photo.write_bytes(b"x")
    out = write_sidecar(_res("reject", str(photo)), preset_xmp=None)
    text = out.read_text(encoding="utf-8")
    assert 'Rating="0"' in text or "Rating=\"0\"" in text


def test_sidecar_embeds_preset_params(tmp_path: Path):
    photo = tmp_path / "look.jpg"
    photo.write_bytes(b"x")
    preset_xmp = (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
        ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        '  <rdf:Description rdf:about=""\n'
        '    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"\n'
        '    crs:Exposure2012="0.35">\n'
        "  </rdf:Description>\n"
        " </rdf:RDF>\n"
        "</x:xmpmeta>\n"
    )
    out = write_sidecar(_res("keep", str(photo)), preset_xmp=preset_xmp)
    text = out.read_text(encoding="utf-8")
    assert "Exposure2012" in text
    # Still valid XML after merging.
    minidom.parseString(text)


def test_sidecar_is_idempotent(tmp_path: Path):
    photo = tmp_path / "idem.jpg"
    photo.write_bytes(b"x")
    res = _res("maybe", str(photo))
    first = write_sidecar(res, preset_xmp=None).read_text(encoding="utf-8")
    second = write_sidecar(res, preset_xmp=None).read_text(encoding="utf-8")
    assert first == second
