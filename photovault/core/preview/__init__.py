"""Preview extraction (stage A): pull pixels from Lightroom preview caches.

Lightroom never needs the original files for L3 learning — the preview cache
holds enough pixels. We support two shapes:

* ``.lrprev`` — a Lua-ish wrapper packing one or more JPEGs; we carve the
  largest embedded JPEG (SOI ``0xFFD8`` .. EOI ``0xFFD9``).
* Smart Preview ``.dng`` — a lossy DNG decoded lazily via ``rawpy``.
"""

from photovault.core.preview.extractor import (
    carve_largest_jpeg,
    extract_preview,
    find_preview,
)

__all__ = ["carve_largest_jpeg", "extract_preview", "find_preview"]
