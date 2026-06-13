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


def test_create_app_importable_without_calling():
    # Importing the module must not require fastapi at import time of the package
    import importlib

    import photovault.api.app as appmod

    importlib.reload(appmod)
    assert hasattr(appmod, "create_app")
