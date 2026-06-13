"""FastAPI app factory for the PhotoVault web UI (M5).

FastAPI is imported lazily inside :func:`create_app` so that importing this
module never hard-requires the optional ``web`` extra. The app serves the React
SPA (``static/``) and backs it with the real M1-M4 pipelines via the pure
:mod:`photovault.api.mappers`.

State: the last ``/api/apply`` result is held on ``app.state`` so ``/api/thumb``
can resolve frame pixels and confine itself to the last-applied folder.
"""

from pathlib import Path
from typing import Any, Optional

from photovault.api import mappers

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Optional[Any] = None):
    """Build the FastAPI application (lazy fastapi import).

    *settings* is an optional injected :class:`~photovault.settings.Settings`
    (tests point ``profiles_dir`` at a temp dir and disable the LLM). When None,
    the process-wide settings are read via ``get_settings``.
    """
    from fastapi import FastAPI, HTTPException, Query, Request
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
    from fastapi.staticfiles import StaticFiles

    from photovault.core.profile.store import load_profile, profile_exists
    from photovault.core.score import apply_to_folder
    from photovault.settings import get_settings

    if settings is None:
        settings = get_settings()

    app = FastAPI(title="PhotoVault", docs_url="/api/docs", redoc_url=None)
    app.state.settings = settings
    # Folder + per-path index of the most recent apply (for /api/thumb confinement).
    app.state.last_folder = None  # type: Optional[Path]
    app.state.last_paths = set()  # type: set[str]

    def _settings():
        return app.state.settings

    # ----------------------------------------------------------------- API --- #
    @app.get("/api/profiles")
    def get_profiles() -> Any:
        return mappers.profiles_list(_settings())

    @app.get("/api/profiles/{name}")
    def get_profile(name: str) -> Any:
        s = _settings()
        if not profile_exists(s.profiles_dir, name):
            raise HTTPException(status_code=404, detail=f"profile not found: {name}")
        prof = load_profile(s.profiles_dir, name)
        return mappers.profile_detail(prof)

    @app.get("/api/settings")
    def get_settings_view() -> Any:
        return mappers.settings_view(_settings())

    @app.post("/api/learn")
    async def post_learn(request: Request) -> Any:
        from photovault.core.learn import learn_from_folder

        body = await request.json()
        catalog_folder = body.get("catalog_folder")
        name = body.get("name")
        no_llm = bool(body.get("no_llm", False))
        if not catalog_folder or not name:
            raise HTTPException(status_code=400, detail="catalog_folder and name required")
        try:
            report = learn_from_folder(
                catalog_folder, name, _settings(), use_llm=not no_llm
            )
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {
            "name": report.name,
            "profile_dir": str(report.profile_dir),
            "n_catalogs": report.n_catalogs,
            "n_images": report.n_images,
            "n_keepers": report.n_keepers,
            "n_rejects": report.n_rejects,
            "n_presets": report.n_presets,
            "llm_used": report.llm_used,
            "llm_note": report.llm_note,
            "pixels_used": report.pixels_used,
            "n_embedded": report.n_embedded,
            "pixels_note": report.pixels_note,
        }

    @app.post("/api/apply")
    async def post_apply(request: Request) -> Any:
        body = await request.json()
        photo_folder = body.get("photo_folder")
        name = body.get("name")
        no_llm = bool(body.get("no_llm", False))
        do_report = bool(body.get("report", False))
        do_sort = bool(body.get("sort", False))
        s = _settings()
        if not photo_folder or not name:
            raise HTTPException(status_code=400, detail="photo_folder and name required")
        if not profile_exists(s.profiles_dir, name):
            raise HTTPException(status_code=404, detail=f"profile not found: {name}")

        folder = Path(photo_folder).expanduser()
        if not folder.is_dir():
            raise HTTPException(status_code=400, detail=f"not a folder: {folder}")

        sort_dir = (folder / "sorted") if do_sort else None
        report = apply_to_folder(
            folder, name, s, report=do_report, sort_dir=sort_dir, no_llm=no_llm
        )

        # Remember the applied folder + the exact set of result paths so
        # /api/thumb can confine itself to them (path-traversal guard).
        app.state.last_folder = folder.resolve()
        app.state.last_paths = {str(Path(r.path).resolve()) for r in report.results}

        return mappers.apply_payload(report, folder)

    @app.get("/api/thumb")
    def get_thumb(path: str = Query(...)):
        last_folder: Optional[Path] = app.state.last_folder
        if last_folder is None:
            raise HTTPException(status_code=404, detail="no applied folder yet")

        # Resolve and confine: the requested path must live inside the last
        # applied folder AND be one of the files we actually scored.
        try:
            resolved = Path(path).resolve()
        except (OSError, RuntimeError):
            raise HTTPException(status_code=400, detail="bad path")
        if not _is_within(resolved, last_folder):
            raise HTTPException(status_code=403, detail="path outside applied folder")
        if str(resolved) not in app.state.last_paths:
            raise HTTPException(status_code=404, detail="not a scored frame")
        if not resolved.is_file():
            raise HTTPException(status_code=404, detail="file not found")

        jpeg = _make_thumbnail(resolved)
        if jpeg is None:
            # Pillow missing or undecodable -> serve the original bytes as a fallback.
            raise HTTPException(status_code=404, detail="cannot render thumbnail")
        return Response(content=jpeg, media_type="image/jpeg")

    # --------------------------------------------------------------- static --- #
    # Mount the React SPA assets (jsx/js/css/png). The index is served at "/".
    if _STATIC_DIR.exists():
        app.mount(
            "/static", StaticFiles(directory=str(_STATIC_DIR)), name="static"
        )

    @app.get("/", response_class=HTMLResponse)
    def index() -> Any:
        index_file = _STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file), media_type="text/html")
        return HTMLResponse(
            "<h1>PhotoVault</h1><p>UI assets not found.</p>", status_code=200
        )

    # Serve the jsx/asset files by bare name too (the design's <script src> tags
    # reference them relative to the page root, e.g. "pv-app.jsx").
    @app.get("/{asset:path}")
    def asset(asset: str):
        if not asset or "/" in asset and asset.startswith(".."):
            raise HTTPException(status_code=404)
        candidate = (_STATIC_DIR / asset).resolve()
        if not _is_within(candidate, _STATIC_DIR.resolve()) or not candidate.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(str(candidate))

    return app


# --------------------------------------------------------------------------- #
# helpers (module-level so they need no fastapi)
# --------------------------------------------------------------------------- #
def _is_within(child: Path, parent: Path) -> bool:
    """True if *child* is inside *parent* (resolved). Python 3.9 safe."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _make_thumbnail(path: Path, max_side: int = 480) -> Optional[bytes]:
    """Render a JPEG thumbnail of *path* (lazy Pillow). None on failure."""
    try:
        import io

        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=82)
            return buf.getvalue()
    except Exception:
        return None
