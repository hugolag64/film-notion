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
    assert {"users", "auth_sessions", "password_reset_tokens"} <= tables


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


def test_deleting_a_user_removes_the_account_and_sessions(tmp_path):
    db = tmp_path / "backstage.db"
    store = AuthStore(str(db))
    store.init_schema()
    store.create_admin("Hugo", "hugo@example.com", "Correct Horse Battery Staple")
    user = store.create_user("Paul", "paul@example.com", "12345678")
    _, token, _ = store.authenticate("paul@example.com", "12345678", True, "Laptop")

    assert store.delete_user(user["id"])
    assert store.user_from_token(token) is None
    assert all(item["id"] != user["id"] for item in store.list_users())


def test_change_password_keeps_current_session_and_revokes_other_sessions(tmp_path):
    db = tmp_path / "backstage.db"
    store = AuthStore(str(db))
    store.init_schema()
    store.create_admin("Hugo", "hugo@example.com", "Correct Horse Battery Staple")
    user = store.create_user("Paul", "paul@example.com", "old-password")
    _, current_token, _ = store.authenticate("paul@example.com", "old-password", False, "Laptop")
    _, other_token, _ = store.authenticate("paul@example.com", "old-password", True, "Phone")
    current_session_id = store.user_from_token(current_token)[1]

    store.change_password(user["id"], "old-password", "new-password", current_session_id)

    assert store.user_from_token(current_token)[0] == user
    assert store.user_from_token(other_token) is None
    with pytest.raises(ValueError, match="invalid credentials"):
        store.authenticate("paul@example.com", "old-password", False, "Browser")
    assert store.authenticate("paul@example.com", "new-password", False, "Browser")[0] == user


def test_change_password_rejects_an_incorrect_current_password(tmp_path):
    db = tmp_path / "backstage.db"
    store = AuthStore(str(db))
    store.init_schema()
    store.create_admin("Hugo", "hugo@example.com", "Correct Horse Battery Staple")
    user = store.create_user("Paul", "paul@example.com", "old-password")
    _, token, _ = store.authenticate("paul@example.com", "old-password", False, "Laptop")
    session_id = store.user_from_token(token)[1]

    with pytest.raises(ValueError, match="invalid current password"):
        store.change_password(user["id"], "wrong-password", "new-password", session_id)


def test_reset_token_changes_password_once_and_revokes_all_sessions(tmp_path):
    db = tmp_path / "backstage.db"
    store = AuthStore(str(db))
    store.init_schema()
    store.create_admin("Hugo", "hugo@example.com", "Correct Horse Battery Staple")
    user = store.create_user("Paul", "paul@example.com", "old-password")
    _, first_token, _ = store.authenticate("paul@example.com", "old-password", False, "Laptop")
    _, second_token, _ = store.authenticate("paul@example.com", "old-password", True, "Phone")
    reset_token, user_id = store.create_password_reset_token("PAUL@example.com")

    assert user_id == user["id"]
    assert store.reset_password(reset_token, "new-password") == user["id"]
    assert store.user_from_token(first_token) is None
    assert store.user_from_token(second_token) is None
    assert store.authenticate("paul@example.com", "new-password", False, "Browser")[0] == user
    with pytest.raises(ValueError, match="invalid or expired reset token"):
        store.reset_password(reset_token, "another-password")


def test_reset_token_is_not_created_for_unknown_or_inactive_email(tmp_path):
    db = tmp_path / "backstage.db"
    store = AuthStore(str(db))
    store.init_schema()
    store.create_admin("Hugo", "hugo@example.com", "Correct Horse Battery Staple")
    user = store.create_user("Paul", "paul@example.com", "old-password")

    assert store.create_password_reset_token("missing@example.com") is None
    store.update_user(user["id"], {"is_active": False})
    assert store.create_password_reset_token("paul@example.com") is None


def test_expired_reset_token_is_rejected(tmp_path):
    db = tmp_path / "backstage.db"
    store = AuthStore(str(db))
    store.init_schema()
    store.create_admin("Hugo", "hugo@example.com", "Correct Horse Battery Staple")
    user = store.create_user("Paul", "paul@example.com", "old-password")
    reset_token = "expired-token"
    now = datetime.now(timezone.utc)
    with sqlite3.connect(db) as connection:
        connection.execute(
            """
            INSERT INTO password_reset_tokens
            (id, user_id, token_hash, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "expired-id", user["id"], store._token_hash(reset_token),
                now.isoformat(), (now.replace(year=now.year - 1)).isoformat(),
            ),
        )

    with pytest.raises(ValueError, match="invalid or expired reset token"):
        store.reset_password(reset_token, "new-password")


def test_admin_set_password_revokes_all_sessions(tmp_path):
    db = tmp_path / "backstage.db"
    store = AuthStore(str(db))
    store.init_schema()
    store.create_admin("Hugo", "hugo@example.com", "Correct Horse Battery Staple")
    user = store.create_user("Paul", "paul@example.com", "old-password")
    _, token, _ = store.authenticate("paul@example.com", "old-password", True, "Laptop")

    store.set_password(user["id"], "new-password")

    assert store.user_from_token(token) is None
    assert store.authenticate("paul@example.com", "new-password", False, "Browser")[0] == user


def test_jellyfin_user_link_can_be_changed_and_removed(tmp_path):
    db = tmp_path / "backstage.db"
    store = AuthStore(str(db))
    store.init_schema()
    store.create_admin("Hugo", "hugo@example.com", "Correct Horse Battery Staple")
    user = store.create_user("Ophélie", "ophelie@example.com", "12345678")

    linked = store.set_jellyfin_user_id(user["id"], "jf-ophelie")
    assert linked["jellyfin_user_id"] == "jf-ophelie"
    assert store.list_users()[1]["jellyfin_user_id"] == "jf-ophelie"

    changed = store.set_jellyfin_user_id(user["id"], "jf-ophelie-2")
    assert changed["jellyfin_user_id"] == "jf-ophelie-2"

    unlinked = store.set_jellyfin_user_id(user["id"], None)
    assert unlinked["jellyfin_user_id"] is None


def test_jellyfin_user_link_rejects_duplicates_and_missing_users(tmp_path):
    db = tmp_path / "backstage.db"
    store = AuthStore(str(db))
    store.init_schema()
    store.create_admin("Hugo", "hugo@example.com", "Correct Horse Battery Staple")
    first = store.create_user("Hugo 2", "hugo2@example.com", "12345678")
    second = store.create_user("Ophélie", "ophelie@example.com", "12345678")

    store.set_jellyfin_user_id(first["id"], "jf-shared")
    with pytest.raises(ValueError, match="jellyfin user already linked"):
        store.set_jellyfin_user_id(second["id"], "jf-shared")
    with pytest.raises(ValueError, match="user not found"):
        store.set_jellyfin_user_id("missing", "jf-missing")
