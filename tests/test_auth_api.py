import httpx
import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient
from urllib.parse import parse_qs, urlparse

import backend.auth_api as auth_module
import backend.api as api_module
from backend.api import router as media_router
from backend.auth_api import auth_router
from backend.config import Config
from backend.core.auth import AuthStore
from backend.core.store import MediaStore
from backend.core.media_server import Availability
from backend.core.arr import MediaServerError


class FakeJellyfinClient:
    users = [
        {"id": "jf-hugo", "name": "Hugo", "is_admin": True},
        {"id": "jf-ophelie", "name": "Ophélie", "is_admin": False},
    ]
    error = None

    def __init__(self, *args, **kwargs):
        pass

    async def list_users(self):
        if self.error:
            raise self.error
        return self.users


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


def test_admin_can_list_and_link_jellyfin_accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(auth_module, "JellyfinClient", FakeJellyfinClient)
    monkeypatch.setattr(Config, "JELLYFIN_API_KEY", "secret")
    FakeJellyfinClient.error = None
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    created = client.post("/api/auth/users", json={
        "display_name": "Ophélie",
        "email": "ophelie@example.com",
        "password": "12345678",
    })
    user_id = created.json()["user"]["id"]

    listed = client.get("/api/auth/jellyfin-users")
    assert listed.status_code == 200
    assert listed.json() == {"users": FakeJellyfinClient.users}

    linked = client.put(
        f"/api/auth/users/{user_id}/jellyfin",
        json={"jellyfin_user_id": "jf-ophelie"},
    )
    assert linked.status_code == 200
    assert linked.json()["user"]["jellyfin_user_id"] == "jf-ophelie"
    assert client.get("/api/auth/me").json()["user"]["jellyfin_user_id"] is None
    assert next(
        user for user in client.get("/api/auth/users").json()["users"]
        if user["id"] == user_id
    )["jellyfin_user_id"] == "jf-ophelie"


def test_jellyfin_link_rejects_invalid_ids_duplicates_and_allows_unlinking(tmp_path, monkeypatch):
    monkeypatch.setattr(auth_module, "JellyfinClient", FakeJellyfinClient)
    monkeypatch.setattr(Config, "JELLYFIN_API_KEY", "secret")
    FakeJellyfinClient.error = None
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    first = client.post("/api/auth/users", json={
        "display_name": "Hugo 2", "email": "hugo2@example.com", "password": "12345678",
    }).json()["user"]["id"]
    second = client.post("/api/auth/users", json={
        "display_name": "Ophélie", "email": "ophelie@example.com", "password": "12345678",
    }).json()["user"]["id"]

    assert client.put(
        f"/api/auth/users/{first}/jellyfin", json={"jellyfin_user_id": "missing"}
    ).status_code == 422
    assert client.put(
        f"/api/auth/users/missing/jellyfin", json={"jellyfin_user_id": "jf-hugo"}
    ).status_code == 404
    assert client.put(
        f"/api/auth/users/{first}/jellyfin", json={"jellyfin_user_id": "jf-hugo"}
    ).status_code == 200
    assert client.put(
        f"/api/auth/users/{second}/jellyfin", json={"jellyfin_user_id": "jf-hugo"}
    ).status_code == 409
    assert client.put(
        f"/api/auth/users/{first}/jellyfin", json={"jellyfin_user_id": None}
    ).status_code == 200


def test_regular_user_cannot_read_or_modify_jellyfin_links(tmp_path, monkeypatch):
    monkeypatch.setattr(auth_module, "JellyfinClient", FakeJellyfinClient)
    monkeypatch.setattr(Config, "JELLYFIN_API_KEY", "secret")
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    created = client.post("/api/auth/users", json={
        "display_name": "Paul", "email": "paul@example.com", "password": "12345678",
    })
    user_id = created.json()["user"]["id"]
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={
        "email": "paul@example.com", "password": "12345678", "remember_device": False,
    })

    assert client.get("/api/auth/jellyfin-users").status_code == 403
    assert client.put(
        f"/api/auth/users/{user_id}/jellyfin", json={"jellyfin_user_id": "jf-ophelie"}
    ).status_code == 403


def test_jellyfin_errors_do_not_erase_existing_links(tmp_path, monkeypatch):
    monkeypatch.setattr(auth_module, "JellyfinClient", FakeJellyfinClient)
    monkeypatch.setattr(Config, "JELLYFIN_API_KEY", "secret")
    FakeJellyfinClient.error = None
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    created = client.post("/api/auth/users", json={
        "display_name": "Ophélie", "email": "ophelie@example.com", "password": "12345678",
    })
    user_id = created.json()["user"]["id"]
    assert client.put(
        f"/api/auth/users/{user_id}/jellyfin", json={"jellyfin_user_id": "jf-ophelie"}
    ).status_code == 200

    FakeJellyfinClient.error = httpx.HTTPError("Jellyfin unavailable")
    assert client.get("/api/auth/jellyfin-users").status_code == 503
    assert client.put(
        f"/api/auth/users/{user_id}/jellyfin", json={"jellyfin_user_id": "jf-hugo"}
    ).status_code == 503
    stored = next(
        user for user in client.get("/api/auth/users").json()["users"]
        if user["id"] == user_id
    )
    assert stored["jellyfin_user_id"] == "jf-ophelie"


def test_playback_routes_use_the_current_users_jellyfin_mapping(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    admin = client.get("/api/auth/me").json()["user"]
    AuthStore(Config.DB_PATH).set_jellyfin_user_id(admin["id"], "jf-hugo")

    class FakePlaybackService:
        async def sync_playback(self, backstage_user_id, jellyfin_user_id):
            assert backstage_user_id == admin["id"]
            assert jellyfin_user_id == "jf-hugo"
            return {"synced": 1}

        async def playback_summary(self, backstage_user_id):
            assert backstage_user_id == admin["id"]
            return {"resume": [], "next_episodes": [], "recently_completed": [], "last_synced_at": None}

    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: FakePlaybackService()
    sync = client.post("/api/playback/sync")
    summary = client.get("/api/playback/summary")

    assert sync.status_code == 200
    assert sync.json() == {"linked": True, "synced": 1}
    assert summary.status_code == 200
    assert summary.json() == {
        "linked": True, "resume": [], "next_episodes": [],
        "recently_completed": [], "last_synced_at": None,
    }


def test_regular_user_can_submit_an_acquisition_request(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    created = client.post("/api/auth/users", json={
        "display_name": "Paul", "email": "paul@example.com", "password": "12345678",
    }).json()["user"]
    media = asyncio.run(MediaStore(Config.DB_PATH).create({
        "id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631,
    }))

    class FakeAcquisitionService:
        store = MediaStore(Config.DB_PATH)
        calls = []

        async def add(self, media, quality_profile_id, root_folder, language_profile_id, monitor):
            self.calls.append((media.id, quality_profile_id, root_folder))
            return Availability(media_id=media.id, provider="radarr", state="requested")

    service = FakeAcquisitionService()
    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: service
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={
        "email": "paul@example.com", "password": "12345678", "remember_device": False,
    })

    response = client.post(f"/api/medias/{media.id}/acquisition", json={
        "quality_profile_id": 5, "root_folder": "/media/movies",
    })

    assert response.status_code == 200
    assert service.calls == [("dune", 5, "/media/movies")]


def test_media_activity_is_admin_only(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)

    class FakeActivityService:
        async def activity(self):
            return {"items": [], "disks": []}

    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: FakeActivityService()
    assert client.get("/api/media-server/activity").status_code == 200

    client.post("/api/auth/users", json={
        "display_name": "Paul", "email": "paul@example.com", "password": "12345678",
    })
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={
        "email": "paul@example.com", "password": "12345678", "remember_device": False,
    })

    assert client.get("/api/media-server/activity").status_code == 403

def test_acquisition_returns_remote_media_server_reason(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    media = asyncio.run(MediaStore(Config.DB_PATH).create({
        "id": "dune", "title": "Dune", "type": "Film", "tmdb_id": 438631,
    }))

    class FailingAcquisitionService:
        store = MediaStore(Config.DB_PATH)

        async def add(self, *args):
            raise MediaServerError("Seerr HTTP 400: No default Radarr server")

    client.app.dependency_overrides[api_module.get_media_server_service] = lambda: FailingAcquisitionService()
    response = client.post(f"/api/medias/{media.id}/acquisition", json={})

    assert response.status_code == 502
    assert response.json() == {"detail": "Seerr HTTP 400: No default Radarr server"}


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


def test_admin_can_change_their_own_display_name(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    admin_id = client.get("/api/auth/me").json()["user"]["id"]

    response = client.patch(
        f"/api/auth/users/{admin_id}",
        json={"display_name": "Hugo Maison"},
    )

    assert response.status_code == 200
    assert client.get("/api/auth/me").json()["user"]["display_name"] == "Hugo Maison"


def test_admin_can_change_another_users_display_name(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    created = client.post("/api/auth/users", json={
        "display_name": "Ophelie",
        "email": "ophelie@example.com",
        "password": "12345678",
    })
    user_id = created.json()["user"]["id"]

    response = client.patch(
        f"/api/auth/users/{user_id}",
        json={"display_name": "Ophélie"},
    )

    assert response.status_code == 200
    assert next(user for user in client.get("/api/auth/users").json()["users"] if user["id"] == user_id)["display_name"] == "Ophélie"


def test_user_can_change_password_and_keep_the_current_session(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    client.post("/api/auth/users", json={
        "display_name": "Paul",
        "email": "paul@example.com",
        "password": "old-password",
    })
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={
        "email": "paul@example.com",
        "password": "old-password",
        "remember_device": True,
    })
    _, other_token, _ = AuthStore(Config.DB_PATH).authenticate(
        "paul@example.com", "old-password", True, "Phone"
    )

    response = client.post("/api/auth/change-password", json={
        "current_password": "old-password",
        "new_password": "new-password",
        "password_confirmation": "new-password",
    })

    assert response.status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    assert AuthStore(Config.DB_PATH).user_from_token(other_token) is None


def test_change_password_rejects_wrong_current_password_and_confirmation(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)

    wrong_current = client.post("/api/auth/change-password", json={
        "current_password": "wrong-password",
        "new_password": "new-password",
        "password_confirmation": "new-password",
    })
    mismatch = client.post("/api/auth/change-password", json={
        "current_password": "Correct Horse Battery Staple",
        "new_password": "new-password",
        "password_confirmation": "different-password",
    })

    assert wrong_current.status_code == 422
    assert mismatch.status_code == 422


class FakeEmailSender:
    deliveries = []

    def send_password_reset(self, recipient, reset_url):
        self.__class__.deliveries.append((recipient, reset_url))


def test_forgot_password_has_a_generic_response_and_sends_to_registered_email(tmp_path, monkeypatch):
    FakeEmailSender.deliveries.clear()
    monkeypatch.setattr(auth_module, "EmailSender", FakeEmailSender, raising=False)
    monkeypatch.setattr(Config, "BACKSTAGE_PUBLIC_URL", "https://backstage.home.arpa")
    client = _client(tmp_path, monkeypatch)
    _setup(client)

    known = client.post("/api/auth/forgot-password", json={"email": "hugo@example.com"})
    unknown = client.post("/api/auth/forgot-password", json={"email": "missing@example.com"})

    assert known.status_code == 202
    assert unknown.status_code == 202
    assert known.json() == unknown.json()
    assert FakeEmailSender.deliveries[0][0] == "hugo@example.com"
    assert FakeEmailSender.deliveries[0][1].startswith("https://backstage.home.arpa/reset-password?token=")


def test_reset_password_consumes_the_link_and_invalidates_existing_sessions(tmp_path, monkeypatch):
    FakeEmailSender.deliveries.clear()
    monkeypatch.setattr(auth_module, "EmailSender", FakeEmailSender, raising=False)
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    response = client.post("/api/auth/forgot-password", json={"email": "hugo@example.com"})
    reset_url = FakeEmailSender.deliveries[0][1]
    token = parse_qs(urlparse(reset_url).query)["token"][0]

    reset = client.post("/api/auth/reset-password", json={
        "token": token,
        "new_password": "new-password",
        "password_confirmation": "new-password",
    })
    reused = client.post("/api/auth/reset-password", json={
        "token": token,
        "new_password": "another-password",
        "password_confirmation": "another-password",
    })

    assert response.status_code == 202
    assert reset.status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert reused.status_code == 400


def test_admin_can_set_another_users_password_but_regular_user_cannot(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    _setup(client)
    created = client.post("/api/auth/users", json={
        "display_name": "Paul",
        "email": "paul@example.com",
        "password": "old-password",
    })
    user_id = created.json()["user"]["id"]

    assert client.patch(
        f"/api/auth/users/{user_id}", json={"password": "admin-set-password"}
    ).status_code == 200
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={
        "email": "paul@example.com",
        "password": "admin-set-password",
        "remember_device": False,
    })

    forbidden = client.patch(
        f"/api/auth/users/{user_id}", json={"password": "user-set-password"}
    )

    assert forbidden.status_code == 403
