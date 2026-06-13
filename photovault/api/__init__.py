"""PhotoVault web UI (M5).

This package serves the provided React SPA design backed by the real M1-M4
pipelines. FastAPI / uvicorn / Pillow are imported lazily (inside functions),
so importing :mod:`photovault.api` — or :mod:`photovault.api.mappers` — never
requires the optional ``web`` extra. Only :func:`photovault.api.app.create_app`
actually touches FastAPI.
"""

from __future__ import annotations

__all__ = ["mappers"]
