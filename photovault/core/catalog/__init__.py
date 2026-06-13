"""Lightroom catalog (``.lrcat`` SQLite) reading and L1/L2 extraction.

Nothing here touches the original RAW files — everything lives inside the
catalog database, opened strictly read-only / immutable.
"""

from photovault.core.catalog.reader import (
    CatalogImage,
    DevelopSettings,
    ExifData,
    find_catalogs,
    iter_images,
    open_ro,
    table_columns,
    table_exists,
)

__all__ = [
    "CatalogImage",
    "DevelopSettings",
    "ExifData",
    "find_catalogs",
    "iter_images",
    "open_ro",
    "table_columns",
    "table_exists",
]
