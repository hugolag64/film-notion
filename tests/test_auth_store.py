import sqlite3
from datetime import datetime, timezone

import pytest

from backend.core.auth import AuthStore, hash_password, verify_password
from backend.core.store import MediaStore


def test_auth_schema_is_added_without_changing_media(tmp_path):
    db = tmp_path / "backstage.db"
    MediaStore(str(db)).init_schema()
    with sqlite3.connect(db) as connection:
        connection.execute(
            "INSERT INTO media (id, title, tmdb_ok) VALUES (?, ?, ?)",
            ("movie-1", "Dune", 1),
        )

    AuthStore(str(db)).init_schema()

    with sqlite3.connect(db) as connection:
        assert connection.execute(
            "SELECT title FROM media WHERE id = 'movie-1'"
        ).fetchone() == ("Dune",)
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"users", "auth_sessions"} <= tables


def test_password_hashes_use_unique_salts_and_verify_only_the_original():
    first = hash_password("Correct Horse Battery Staple")
    second = hash_password("Correct Horse Battery Staple")

    assert first != second
    assert verify_password("Correct Horse Battery Staple", first)
    assert not verify_password("wrong password", first)


def test_admin_login_creates_a_24_hour_session_or_a_30_day_session(tmp_path):
    db = tmp_path / "backstage.db"
    store = AuthStore(str(db))
    store.init_schema()
    admin = store.create_admin("Hugo", "HUGO@example.com", "Correct Horse Battery Staple")

    user, normal_token, normal_expiry = store.authenticate(
        "hugo@example.com", "Correct Horse Battery Staple", False, "Chrome"
    )
    _, remembered_token, remembered_expiry = store.authenticate(
        "hugo@example.com", "Correct Horse Battery Staple", True, "Phone"
    )

    assert user == admin
    now = datetime.now(timezone.utc)
    assert 23 * 3600 < (normal_expiry - now).total_seconds() < 25 * 3600
    assert 29 * 86400 < (remembered_expiry - now).total_seconds() < 31 * 86400
    assert store.user_from_token(normal_token)[0] == admin
    assert store.user_from_token(remembered_token)[0] == admin


def test_only_one_admin_can_be_created_and_last_admin_is_protected(tmp_path):
    db = tmp_path / "backstage.db"
    store = AuthStore(str(db))
    store.init_schema()
    admin = store.create_admin("Hugo", "hugo@example.com", "Correct Horse Battery Staple")

    with pytest.raises(ValueError, match="administrator"):
        store.create_admin("Other", "other@example.com", "Correct Horse Battery Staple")
    with pytest.raises(ValueError, match="last administrator"):
        store.update_user(admin["id"], {"is_active": False})
    with pytest.raises(ValueError, match="last administrator"):
        store.update_user(admin["id"], {"role": "user"})


def test_deactivating_a_user_revokes_their_sessions(tmp_path):
    db = tmp_path / "backstage.db"
    store = AuthStore(str(db))
    store.init_schema()
    store.create_admin("Hugo", "hugo@example.com", "Correct Horse Battery Staple")
    user = store.create_user("Paul", "paul@example.com", "Correct Horse Battery Staple")
    _, token, _ = store.authenticate(
        "paul@example.com", "Correct Horse Battery Staple", True, "Laptop"
    )

    store.update_user(user["id"], {"is_active": False})

    assert store.user_from_token(token) is None
