"""Stage-B outputs: XMP sidecars, HTML review report, optional foldering (M3)."""

from photovault.core.export.csv_report import write_decisions_csv
from photovault.core.export.foldering import sort_into_folders
from photovault.core.export.report import render_report, write_report
from photovault.core.export.xmp import build_sidecar_xmp, rating_for, write_sidecar

__all__ = [
    "build_sidecar_xmp",
    "rating_for",
    "render_report",
    "sort_into_folders",
    "write_decisions_csv",
    "write_report",
    "write_sidecar",
]
