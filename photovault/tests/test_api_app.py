"""TDD for the FastAPI app: endpoints via TestClient, no network, no models."""

from __future__ import annotations

from pathlib import Path

import pytest

from photovault.settings import Settings

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from photovault.api.app import create_app  # noqa: E402


@pytest.fixture
def client(settings: Settings):
    app = create_app(settings=settings)
    return TestClient(app)


# --------------------------------------------------------------------------- #
# static / index
# --------------------------------------------------------------------------- #
def test_index_serves_html(client: TestClient):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<div id=\"root\">" in r.text or "<div id='root'>" in r.text


# --------------------------------------------------------------------------- #
# profiles
# --------------------------------------------------------------------------- #
def test_profiles_empty(client: TestClient):
    r = client.get("/api/profiles")
    assert r.status_code == 200
    assert r.json() == []


def test_profiles_list(settings: Settings, learned_profile: str):
    app = create_app(settings=settings)
    client = TestClient(app)
    r = client.get("/api/profiles")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["id"] == "taste"
    assert "keepRate" in data[0]


def test_profile_detail(settings: Settings, learned_profile: str):
    client = TestClient(create_app(settings=settings))
    r = client.get("/api/profiles/taste")
    assert r.status_code == 200
    data = r.json()
    assert data["meta"]["name"] == "taste"
    assert "thresholds" in data
    assert "presets" in data
    assert "profileMd" in data


def test_profile_detail_missing(client: TestClient):
    r = client.get("/api/profiles/nope")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# settings
# --------------------------------------------------------------------------- #
def test_settings_endpoint(client: TestClient, settings: Settings):
    r = client.get("/api/settings")
    assert r.status_code == 200
    data = r.json()
    assert data["cull"]["keep_rating"] == settings.cull.keep_rating
    assert data["llm"]["enabled"] is False


# --------------------------------------------------------------------------- #
# apply + thumb (security)
# --------------------------------------------------------------------------- #
def test_apply_and_thumb(settings: Settings, learned_profile: str, new_photos: Path):
    client = TestClient(create_app(settings=settings))
    r = client.post(
        "/api/apply",
        json={"photo_folder": str(new_photos), "name": "taste", "no_llm": True},
    )
    assert r.status_code == 200
    data = r.json()
    assert "frames" in data and data["frames"]
    assert data["bandCounts"]["total"] == len(data["frames"])

    # A real thumbnail can be fetched for a frame in the applied folder.
    src = data["frames"][0]["src"]
    tr = client.get(src)
    assert tr.status_code == 200
    assert tr.headers["content-type"] in ("image/jpeg", "image/jpg")
    assert len(tr.content) > 0


def test_thumb_path_traversal_blocked(settings: Settings, learned_profile: str, new_photos: Path, tmp_path: Path):
    client = TestClient(create_app(settings=settings))
    # establish a last-applied folder
    client.post(
        "/api/apply",
        json={"photo_folder": str(new_photos), "name": "taste", "no_llm": True},
    )
    # a secret file OUTSIDE the applied folder
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret")
    r = client.get("/api/thumb", params={"path": str(secret)})
    assert r.status_code in (403, 404)
    # also block traversal via ../
    r2 = client.get("/api/thumb", params={"path": str(new_photos / ".." / "secret.txt")})
    assert r2.status_code in (403, 404)


def test_thumb_before_apply(client: TestClient):
    r = client.get("/api/thumb", params={"path": "/etc/passwd"})
    assert r.status_code in (403, 404)


def test_apply_missing_profile(client: TestClient, new_photos: Path):
    r = client.post(
        "/api/apply",
        json={"photo_folder": str(new_photos), "name": "nope", "no_llm": True},
    )
    assert r.status_code == 404


def test_learn_with_multiple_folders(settings: Settings, catalog_folder: Path, tmp_path: Path):
    # A second catalog folder so the API has >1 root to aggregate.
    from photovault.tests.make_fake import default_images, write_catalog

    folder2 = tmp_path / "more_catalogs"
    folder2.mkdir()
    write_catalog(folder2 / "shoot2.lrcat", default_images())

    client = TestClient(create_app(settings=settings))
    r = client.post(
        "/api/learn",
        json={
            "catalog_folders": [str(catalog_folder), str(folder2)],
            "name": "multi",
            "no_llm": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["name"] == "multi"
    assert data["n_catalogs"] == 2  # both roots' catalogs aggregated


def test_learn_requires_folders_and_name(client: TestClient):
    r = client.post("/api/learn", json={"catalog_folders": [], "name": "x"})
    assert r.status_code == 400


def test_learn_name_optional_defaults_to_folder(settings: Settings, catalog_folder: Path):
    client = TestClient(create_app(settings=settings))
    # No name given -> defaults to the folder's basename.
    r = client.post("/api/learn", json={"catalog_folders": [str(catalog_folder)], "no_llm": True})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == catalog_folder.name


def test_learn_response_includes_skip_log(settings: Settings, catalog_folder: Path, tmp_path: Path):
    from photovault.tests.make_fake import FakeImage, write_catalog

    blank = tmp_path / "blankroot"
    blank.mkdir()
    write_catalog(
        blank / "blank.lrcat",
        [FakeImage(base_name="x", capture_time="2024-01-01T00:00:00")],
    )
    client = TestClient(create_app(settings=settings))
    r = client.post(
        "/api/learn",
        json={"catalog_folders": [str(catalog_folder), str(blank)], "name": "mix", "no_llm": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["n_skipped"] == 1
    assert any("blank.lrcat" in line for line in body["log"])


def test_learn_stream_emits_progress_and_done(settings: Settings, catalog_folder: Path):
    import json

    client = TestClient(create_app(settings=settings))
    events = []
    with client.stream(
        "POST",
        "/api/learn/stream",
        json={"catalog_folders": [str(catalog_folder)], "no_llm": True},
    ) as r:
        assert r.status_code == 200
        for line in r.iter_lines():
            if line.strip():
                events.append(json.loads(line))

    phases = [e["phase"] for e in events]
    assert "scan" in phases and "catalog" in phases and "done" in phases
    cat = next(e for e in events if e["phase"] == "catalog")
    assert cat["name"] == "shoot.lrcat" and "ratings" in cat["stats"]
    done = next(e for e in events if e["phase"] == "done")
    assert done["report"]["name"] == catalog_folder.name


def test_learn_stream_error_event(client: TestClient, tmp_path: Path):
    import json

    empty = tmp_path / "empty"
    empty.mkdir()
    events = []
    with client.stream(
        "POST", "/api/learn/stream", json={"catalog_folders": [str(empty)]}
    ) as r:
        for line in r.iter_lines():
            if line.strip():
                events.append(json.loads(line))
    assert any(e["phase"] == "error" for e in events)


def test_pick_folder_returns_dialog_path(client: TestClient, monkeypatch):
    # The native dialog is mocked (no real Finder in CI / on Linux).
    import photovault.api.app as appmod

    monkeypatch.setattr(appmod, "_pick_folder_dialog", lambda: "/Users/tim/Lightroom")
    monkeypatch.setattr(appmod, "_picker_supported", lambda: True)
    r = client.post("/api/pick-folder")
    assert r.status_code == 200
    body = r.json()
    assert body["path"] == "/Users/tim/Lightroom"
    assert body["supported"] is True


def test_pick_folder_cancelled_returns_null(client: TestClient, monkeypatch):
    import photovault.api.app as appmod

    monkeypatch.setattr(appmod, "_pick_folder_dialog", lambda: None)
    r = client.post("/api/pick-folder")
    assert r.status_code == 200
    assert r.json()["path"] is None


def test_create_app_importable_without_calling():
    # Importing the module must not require fastapi at import time of the package
    import importlib

    import photovault.api.app as appmod

    importlib.reload(appmod)
    assert hasattr(appmod, "create_app")
