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
    from fastapi.responses import (
        FileResponse,
        HTMLResponse,
        JSONResponse,
        Response,
        StreamingResponse,
    )
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
        # Accept either a single `catalog_folder` (back-compat) or a list of
        # `catalog_folders` (the UI's add-multiple-folders flow).
        folders = body.get("catalog_folders")
        if not folders:
            single = body.get("catalog_folder")
            folders = [single] if single else []
        folders = [f for f in folders if f]
        if not folders:
            raise HTTPException(status_code=400, detail="catalog_folders required")
        # Profile name is optional: default to the (first) folder's basename so
        # the user doesn't have to type one.
        name = (body.get("name") or "").strip()
        if not name:
            name = Path(folders[0]).name or "profile"
        no_llm = bool(body.get("no_llm", False))
        try:
            report = learn_from_folder(
                folders, name, _settings(), use_llm=not no_llm
            )
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return _learn_report_json(report)

    @app.post("/api/learn/stream")
    async def post_learn_stream(request: Request):
        """Run learn while streaming live progress as newline-delimited JSON.

        Each line is one event: ``scan`` (catalog count), ``catalog`` (per-file
        name + star/color histogram + kept/skip), ``stats`` / ``style`` /
        ``gemma`` / ``save`` phases, then ``done`` (full report) or ``error``.
        The learn runs in a worker thread; events flow through a queue so the
        UI updates as each catalog is read.
        """
        import json
        import queue
        import threading

        from photovault.core.learn import learn_from_folder

        body = await request.json()
        folders = body.get("catalog_folders")
        if not folders:
            single = body.get("catalog_folder")
            folders = [single] if single else []
        folders = [f for f in folders if f]
        if not folders:
            raise HTTPException(status_code=400, detail="catalog_folders required")
        name = (body.get("name") or "").strip() or (Path(folders[0]).name or "profile")
        no_llm = bool(body.get("no_llm", False))
        s = _settings()

        events: "queue.Queue" = queue.Queue()
        sentinel = object()

        def run() -> None:
            try:
                report = learn_from_folder(
                    folders, name, s, use_llm=not no_llm, progress=events.put
                )
                events.put({"phase": "done", "report": _learn_report_json(report)})
            except Exception as exc:  # surface any failure to the client
                events.put({"phase": "error", "detail": str(exc)})
            finally:
                events.put(sentinel)

        threading.Thread(target=run, daemon=True).start()

        def emit():
            while True:
                ev = events.get()
                if ev is sentinel:
                    break
                yield json.dumps(ev, ensure_ascii=False) + "\n"

        return StreamingResponse(emit(), media_type="application/x-ndjson")

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

    @app.post("/api/pick-folder")
    def pick_folder() -> Any:
        """Open a native OS folder chooser and return the picked absolute path.

        Because the backend runs on the user's own machine, it can show a real
        folder dialog (macOS ``osascript``) so the user never types a path.
        Returns ``{"path": <abs|null>, "supported": <bool>}`` — ``path`` is null
        when the user cancelled or no native picker is available (the UI then
        falls back to manual entry).
        """
        return {"path": _pick_folder_dialog(), "supported": _picker_supported()}

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


def _learn_report_json(report: Any) -> dict:
    """Serialize a LearnReport to the JSON the UI consumes (shared by both
    the blocking and streaming learn endpoints)."""
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
        "n_skipped": report.n_skipped,
        "skipped": report.skipped,
        "log": report.log,
    }


def _picker_supported() -> bool:
    """True if a native folder dialog is available (macOS only for now)."""
    import sys

    return sys.platform == "darwin"


def _pick_folder_dialog() -> Optional[str]:
    """Show a native folder chooser and return its POSIX path.

    macOS-only (uses ``osascript``). Returns None if the user cancelled, the
    picker is unavailable, or it errored — callers treat None as "no path".
    """
    import subprocess
    import sys

    if sys.platform != "darwin":
        return None
    script = (
        'POSIX path of (choose folder with prompt '
        '"選擇資料夾 · Choose a folder for PhotoVault")'
    )
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:  # user cancelled the dialog
        return None
    path = proc.stdout.strip()
    return path or None


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
