from __future__ import annotations

from photovault.core.catalog.cull_logic import (
    Label,
    compute_stats,
    group_bursts,
    label_for,
    parse_capture_time,
)
from photovault.core.catalog.reader import iter_images, open_ro
from photovault.settings import CullSettings


def _load(catalog_path):
    conn = open_ro(catalog_path)
    imgs = list(iter_images(conn))
    conn.close()
    return imgs


def test_label_for_rules():
    cfg = CullSettings()
    from photovault.core.catalog.reader import CatalogImage, DevelopSettings, ExifData

    def mk(rating=None, pick=0):
        return CatalogImage(
            id_local=1, base_name="x", extension="dng", file_format="RAW",
            capture_time=None, rating=rating, pick=pick, color_label=None,
            width=None, height=None, exif=ExifData(), develop=DevelopSettings(),
        )

    assert label_for(mk(pick=1), cfg) is Label.KEEP
    assert label_for(mk(pick=-1), cfg) is Label.REJECT
    assert label_for(mk(rating=5), cfg) is Label.KEEP
    assert label_for(mk(rating=0), cfg) is Label.REJECT
    assert label_for(mk(rating=2), cfg) is Label.UNLABELED  # between thresholds
    assert label_for(mk(), cfg) is Label.UNLABELED
    # pick overrides rating
    assert label_for(mk(rating=0, pick=1), cfg) is Label.KEEP


def test_parse_capture_time_variants():
    assert parse_capture_time(None) is None
    assert parse_capture_time("not a date") is None
    assert parse_capture_time("2023-05-01T14:30:21").year == 2023
    assert parse_capture_time("2023:05:01 14:30:21").month == 5


def test_burst_grouping(catalog_path):
    imgs = _load(catalog_path)
    cfg = CullSettings(burst_gap_seconds=2.0, burst_min_frames=3)
    bursts = group_bursts(imgs, cfg)
    sizes = sorted(b.size for b in bursts)
    # one 5-frame burst, the rest singletons (6 of them)
    assert 5 in sizes
    assert sizes.count(1) == 6


def test_compute_stats(catalog_path):
    imgs = _load(catalog_path)
    cfg = CullSettings()
    stats = compute_stats(imgs, cfg)
    s = stats.summary()

    assert s["total"] == 11
    # keepers: burst last2 + 2 portraits + 2 scapes = 6
    assert s["keepers"] == 6
    # rejects: burst first3 + blink = 4
    assert s["rejects"] == 4
    assert s["unlabeled"] == 1
    assert s["keep_rate"] == round(6 / 10, 3)

    # back-of-burst preference -> position mean clearly > 0.5
    assert s["bursts"]["n_multishot_bursts"] == 1
    assert s["bursts"]["keep_position_mean"] > 0.6

    # keeper aperture median should be wide (lots of f/1.4 and f/2)
    assert s["aperture_f"]["median"] <= 2.0
