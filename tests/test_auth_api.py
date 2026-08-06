from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import router as media_router
from backend.auth_api import auth_router
from backend.config import Config
from backend.core.auth import AuthStore
from backend.core.store import MediaStore


def _client(tmp_path, monkeypatch):
    db = tmp_path / "backstage.db"
    MediaStore(str(db)).init_schema()
    AuthStore(str(db)).init_schema()
    monkeypatch.setattr(Config, "DB_PATH", str(db))
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(media_router)
    return TestClient(app)


def _setup(client):
    return client.post(
        "/api/auth/setup",
        json={
            "display_name": "Hugo",
            "email": "hugo@example.com",
            "password": "Correct Horse Battery Staple",
            "password_confirmation": "Correct Horse Battery Staple",
        },
    )


def test_first_setup_creates_admin_and_cannot_be_repeated(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    assert client.get("/api/auth/status").json() == {"setup_required": True}
    response = _setup(client)

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "admin"
    assert "backstage_session" in response.cookies
    assert client.get("/api/auth/status").json() == {"setup_required": False}
    assert client.post(
        "/api/auth/setup",
        json={
            "display_name": "Other",
            "email": "other@example.com",
            "password": "Correct Horse Battery Staple",
            "password_confirmation": "Correct Horse Battery Staple",
        },
    ).status_code == 409


def test_login_me_and_logout_use_the_session_cookie(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    client.post("/api/auth/logout")

    invalid = client.post(
        "/api/auth/login",
        json={"email": "hugo@example.com", "password": "wrong", "remember_device": False},
    )
    assert invalid.status_code == 401
    assert invalid.json() == {"detail": "Identifiants invalides"}

    login = client.post(
        "/api/auth/login",
        json={
            "email": "HUGO@example.com",
            "password": "Correct Horse Battery Staple",
            "remember_device": True,
        },
    )
    assert login.status_code == 200
    assert client.get("/api/auth/me").json()["user"]["email"] == "hugo@example.com"

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_regular_user_cannot_list_users(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    client.post("/api/auth/users", json={
        "display_name": "Paul",
        "email": "paul@example.com",
        "password": "Correct Horse Battery Staple",
    })
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={
        "email": "paul@example.com",
        "password": "Correct Horse Battery Staple",
        "remember_device": False,
    })

    assert client.get("/api/auth/users").status_code == 403


def test_media_catalog_requires_authentication(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    assert client.get("/api/medias").status_code == 401


def test_revoke_other_devices_keeps_the_current_session(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={
        "email": "hugo@example.com",
        "password": "Correct Horse Battery Staple",
        "remember_device": True,
    })
    _, second_token, _ = AuthStore(Config.DB_PATH).authenticate(
        "hugo@example.com", "Correct Horse Battery Staple", True, "Phone"
    )
    client.cookies.set("backstage_session", second_token)

    response = client.post("/api/auth/devices/revoke-others")

    assert response.status_code == 200
    assert response.json()["revoked"] == 1
    assert len(client.get("/api/auth/devices").json()["devices"]) == 1


def test_user_cannot_revoke_another_users_device(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    client.post("/api/auth/users", json={
        "display_name": "Paul",
        "email": "paul@example.com",
        "password": "Correct Horse Battery Staple",
    })
    admin_devices = client.get("/api/auth/devices").json()["devices"]
    admin_session_id = admin_devices[0]["id"]
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={
        "email": "paul@example.com",
        "password": "Correct Horse Battery Staple",
        "remember_device": False,
    })

    assert client.delete(f"/api/auth/devices/{admin_session_id}").status_code == 204
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={
        "email": "hugo@example.com",
        "password": "Correct Horse Battery Staple",
        "remember_device": False,
    })
    assert len(client.get("/api/auth/devices").json()["devices"]) == 1


def test_admin_can_delete_a_user_but_not_themselves(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    created = client.post("/api/auth/users", json={
        "display_name": "Paul",
        "email": "paul@example.com",
        "password": "12345678",
    })
    user_id = created.json()["user"]["id"]

    assert client.delete(f"/api/auth/users/{user_id}").status_code == 204
    assert all(user["id"] != user_id for user in client.get("/api/auth/users").json()["users"])
    assert client.delete(
        f"/api/auth/users/{created.json()['user']['id']}"
    ).status_code == 404

    admin_id = client.get("/api/auth/me").json()["user"]["id"]
    assert client.delete(f"/api/auth/users/{admin_id}").status_code == 400
