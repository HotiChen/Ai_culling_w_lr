"""L2 culling logic: keep/reject labels, burst grouping and statistics.

This module never reads pixels — it derives everything from catalog metadata
(ratings, flags, capture time, EXIF). The output feeds both the human-readable
profile and the metadata classifier trained in later milestones.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from photovault.core.catalog.reader import CatalogImage
from photovault.settings import CullSettings


class Label(str, Enum):
    KEEP = "keep"
    REJECT = "reject"
    UNLABELED = "unlabeled"


def label_for(img: CatalogImage, cfg: CullSettings) -> Label:
    """Turn a Lightroom rating/flag into a training label.

    Flags win over star ratings (an explicit pick/reject is the strongest
    signal). Mid-rated, unflagged shots are left UNLABELED so they don't add
    noise to the classifier — but they still count in the statistics.
    """
    if img.pick == 1:
        return Label.KEEP
    if img.pick == -1:
        return Label.REJECT
    if img.rating is not None:
        if img.rating >= cfg.keep_rating:
            return Label.KEEP
        if img.rating <= cfg.reject_rating:
            return Label.REJECT
    return Label.UNLABELED


# --------------------------------------------------------------------------- #
# Capture-time parsing
# --------------------------------------------------------------------------- #
def parse_capture_time(value: str | None) -> datetime | None:
    """Parse Lightroom's capture-time text into a datetime.

    Lightroom stores values like ``2023-05-01T14:30:21`` (sometimes with a
    timezone or fractional seconds). We try a few tolerant strategies.
    """
    if not value:
        return None
    text = value.strip()
    # Normalize a trailing 'Z' and space separators.
    candidate = text.replace("Z", "+00:00").replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y:%m:%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------- #
# Burst grouping
# --------------------------------------------------------------------------- #
@dataclass
class Burst:
    """A run of frames shot close together in time."""

    images: list[CatalogImage]

    @property
    def size(self) -> int:
        return len(self.images)


def group_bursts(images: list[CatalogImage], cfg: CullSettings) -> list[Burst]:
    """Group images into bursts by capture-time proximity.

    Images lacking a parseable capture time each become their own singleton
    burst (they can't be sequenced reliably).
    """
    timed: list[tuple[datetime, CatalogImage]] = []
    untimed: list[CatalogImage] = []
    for img in images:
        ts = parse_capture_time(img.capture_time)
        if ts is None:
            untimed.append(img)
        else:
            timed.append((ts, img))

    timed.sort(key=lambda x: x[0])

    bursts: list[Burst] = []
    current: list[CatalogImage] = []
    last_ts: datetime | None = None
    for ts, img in timed:
        if last_ts is not None and (ts - last_ts).total_seconds() <= cfg.burst_gap_seconds:
            current.append(img)
        else:
            if current:
                bursts.append(Burst(current))
            current = [img]
        last_ts = ts
    if current:
        bursts.append(Burst(current))

    bursts.extend(Burst([img]) for img in untimed)
    return bursts


# --------------------------------------------------------------------------- #
# Statistics (L2)
# --------------------------------------------------------------------------- #
@dataclass
class CullStats:
    total: int = 0
    keepers: int = 0
    rejects: int = 0
    unlabeled: int = 0

    keep_rate: float = 0.0  # keepers / labeled

    # EXIF distributions over keepers.
    aperture_keep: list[float] = field(default_factory=list)
    iso_keep: list[int] = field(default_factory=list)
    focal_keep: list[float] = field(default_factory=list)

    # Burst behavior.
    n_bursts: int = 0
    n_multishot_bursts: int = 0
    burst_keep_rate: float = 0.0       # keepers per multishot-burst frame
    keep_position_mean: float = 0.0    # 0 = front of burst, 1 = back

    def _pct(self, values: list[float]) -> dict[str, float]:
        if not values:
            return {}
        s = sorted(values)
        return {
            "min": round(s[0], 3),
            "median": round(statistics.median(s), 3),
            "max": round(s[-1], 3),
            "mean": round(statistics.fmean(s), 3),
        }

    def summary(self) -> dict:
        return {
            "total": self.total,
            "keepers": self.keepers,
            "rejects": self.rejects,
            "unlabeled": self.unlabeled,
            "keep_rate": round(self.keep_rate, 3),
            "aperture_f": self._pct([float(v) for v in self.aperture_keep]),
            "iso": self._pct([float(v) for v in self.iso_keep]),
            "focal_length": self._pct([float(v) for v in self.focal_keep]),
            "bursts": {
                "n_bursts": self.n_bursts,
                "n_multishot_bursts": self.n_multishot_bursts,
                "burst_keep_rate": round(self.burst_keep_rate, 3),
                "keep_position_mean": round(self.keep_position_mean, 3),
            },
        }


def compute_stats(images: list[CatalogImage], cfg: CullSettings) -> CullStats:
    """Compute L2 culling statistics across the catalog."""
    stats = CullStats(total=len(images))

    for img in images:
        lbl = label_for(img, cfg)
        if lbl is Label.KEEP:
            stats.keepers += 1
            if img.exif.aperture_f is not None:
                stats.aperture_keep.append(img.exif.aperture_f)
            if img.exif.iso is not None:
                stats.iso_keep.append(img.exif.iso)
            if img.exif.focal_length is not None:
                stats.focal_keep.append(img.exif.focal_length)
        elif lbl is Label.REJECT:
            stats.rejects += 1
        else:
            stats.unlabeled += 1

    labeled = stats.keepers + stats.rejects
    stats.keep_rate = stats.keepers / labeled if labeled else 0.0

    # Burst analysis.
    bursts = group_bursts(images, cfg)
    stats.n_bursts = len(bursts)
    multishot_keepers = 0
    multishot_frames = 0
    positions: list[float] = []
    for burst in bursts:
        if burst.size < cfg.burst_min_frames:
            continue
        stats.n_multishot_bursts += 1
        multishot_frames += burst.size
        for idx, img in enumerate(burst.images):
            if label_for(img, cfg) is Label.KEEP:
                multishot_keepers += 1
                # Normalize position to [0, 1]; single-frame guard already passed.
                positions.append(idx / (burst.size - 1))
    stats.burst_keep_rate = (
        multishot_keepers / multishot_frames if multishot_frames else 0.0
    )
    stats.keep_position_mean = statistics.fmean(positions) if positions else 0.0

    return stats
