from __future__ import annotations

from photovault.core.catalog.reader import iter_images, open_ro
from photovault.core.catalog.style import (
    STYLE_KEYS,
    Preset,
    extract_style,
    preset_to_xmp,
)
from photovault.settings import StyleSettings


def _load(catalog_path):
    conn = open_ro(catalog_path)
    imgs = list(iter_images(conn))
    conn.close()
    return imgs


def test_extract_style_clusters(catalog_path):
    imgs = _load(catalog_path)
    cfg = StyleSettings(n_presets=3)
    result = extract_style(imgs, cfg)

    # Edited images: 2 burst-keepers (warm) + 2 portraits (warm) + 2 scapes (cool) = 6
    assert result.n_samples == 6
    assert 1 <= len(result.presets) <= 3
    assert result.signature is not None

    # Presets sorted by support descending.
    supports = [p.support for p in result.presets]
    assert supports == sorted(supports, reverse=True)
    # Total support equals samples.
    assert sum(supports) == 6

    # Signature carries all style keys.
    assert set(result.signature.params.keys()) == set(STYLE_KEYS)


def test_extract_style_no_edits(catalog_path):
    # Strip develop settings: all-zero -> no presets.
    imgs = [im for im in _load(catalog_path)]
    for im in imgs:
        object.__setattr__(im.develop, "params", {})
    result = extract_style(imgs, StyleSettings())
    assert result.presets == []
    assert result.signature is None
    assert result.n_samples == 0


def test_preset_to_xmp_wellformed():
    import xml.dom.minidom as minidom

    preset = Preset(name="look_1", params={"Exposure2012": 0.35, "Contrast2012": 10,
                                           "Temperature": 5600})
    xmp = preset_to_xmp(preset)
    # Parses as XML and carries the crs namespace + values.
    minidom.parseString(xmp)
    assert 'crs:Exposure2012="0.35"' in xmp
    assert 'crs:Contrast2012="10"' in xmp  # integer formatting, no .0
    assert 'crs:Name="look_1"' in xmp


def test_determinism(catalog_path):
    imgs = _load(catalog_path)
    cfg = StyleSettings(n_presets=3, random_seed=7)
    a = extract_style(imgs, cfg)
    b = extract_style(imgs, cfg)
    assert [p.params for p in a.presets] == [p.params for p in b.presets]
