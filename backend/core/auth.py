"""SQLite-backed authentication primitives for Backstage."""

import base64
import hashlib
import hmac
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict


_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


class AuthUser(TypedDict):
    id: str
    display_name: str
    email: str
    role: str
    is_active: bool
    jellyfin_user_id: str | None


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    encode = lambda value: base64.urlsafe_b64encode(value).decode("ascii")
    return f"scrypt$N={_SCRYPT_N}$r={_SCRYPT_R}$p={_SCRYPT_P}${encode(salt)}${encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n_part, r_part, p_part, salt_text, digest_text = encoded.split("$")
        if algorithm != "scrypt":
            return False
        n = int(n_part.removeprefix("N="))
        r = int(r_part.removeprefix("r="))
        p = int(p_part.removeprefix("p="))
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(expected)
        )
    except (ValueError, TypeError, UnicodeError):
        return False
    return hmac.compare_digest(actual, expected)


class AuthStore:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def init_schema(self) -> None:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(users)").fetchall()
            }
            if "jellyfin_user_id" not in columns:
                connection.execute("ALTER TABLE users ADD COLUMN jellyfin_user_id TEXT")
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_jellyfin_user_id "
                "ON users(jellyfin_user_id) WHERE jellyfin_user_id IS NOT NULL"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    remember_device INTEGER NOT NULL DEFAULT 0,
                    revoked_at TEXT,
                    user_agent TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions(user_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry ON auth_sessions(expires_at)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS password_reset_tokens (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_expiry "
                "ON password_reset_tokens(user_id, expires_at)"
            )

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _row_to_user(row: sqlite3.Row) -> AuthUser:
        return {
            "id": row["id"],
            "display_name": row["display_name"],
            "email": row["email"],
            "role": row["role"],
            "is_active": bool(row["is_active"]),
            "jellyfin_user_id": row["jellyfin_user_id"],
        }

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _insert_user(
        self, connection: sqlite3.Connection, display_name: str, email: str,
        password: str, role: str,
    ) -> AuthUser:
        if not display_name.strip() or not email.strip() or not password:
            raise ValueError("display name, email and password are required")
        now = self._now().isoformat()
        user_id = str(uuid.uuid4())
        try:
            connection.execute(
                """
                INSERT INTO users (id, display_name, email, password_hash, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id, display_name.strip(), self._normalize_email(email),
                    hash_password(password), role, now, now,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError("email already exists") from error
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return self._row_to_user(row)

    def create_admin(self, display_name: str, email: str, password: str) -> AuthUser:
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM users WHERE role = 'admin' LIMIT 1").fetchone():
                raise ValueError("administrator already exists")
            return self._insert_user(connection, display_name, email, password, "admin")

    def create_user(self, display_name: str, email: str, password: str) -> AuthUser:
        with sqlite3.connect(self.db_path) as connection:
            return self._insert_user(connection, display_name, email, password, "user")

    def _cleanup_sessions(self, connection: sqlite3.Connection, now: datetime) -> None:
        connection.execute(
            "DELETE FROM auth_sessions WHERE revoked_at IS NOT NULL OR expires_at <= ?",
            (now.isoformat(),),
        )

    def authenticate(
        self, email: str, password: str, remember_device: bool, user_agent: str | None,
    ) -> tuple[AuthUser, str, datetime]:
        now = self._now()
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            self._cleanup_sessions(connection, now)
            row = connection.execute(
                "SELECT * FROM users WHERE email = ?", (self._normalize_email(email),)
            ).fetchone()
            if not row or not row["is_active"] or not verify_password(password, row["password_hash"]):
                raise ValueError("invalid credentials")
            token = secrets.token_urlsafe(32)
            expires_at = now + timedelta(days=30 if remember_device else 1)
            connection.execute(
                """
                INSERT INTO auth_sessions
                (id, user_id, token_hash, created_at, expires_at, last_seen_at, remember_device, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()), row["id"], self._token_hash(token), now.isoformat(),
                    expires_at.isoformat(), now.isoformat(), int(remember_device), user_agent,
                ),
            )
            return self._row_to_user(row), token, expires_at

    def user_from_token(self, token: str) -> tuple[AuthUser, str] | None:
        now = self._now()
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                """
                SELECT auth_sessions.id AS session_id, auth_sessions.expires_at,
                       users.*
                FROM auth_sessions
                JOIN users ON users.id = auth_sessions.user_id
                WHERE auth_sessions.token_hash = ?
                  AND auth_sessions.revoked_at IS NULL
                """,
                (self._token_hash(token),),
            ).fetchone()
            if not row or row["expires_at"] <= now.isoformat() or not row["is_active"]:
                return None
            connection.execute(
                "UPDATE auth_sessions SET last_seen_at = ? WHERE id = ?",
                (now.isoformat(), row["session_id"]),
            )
            return self._row_to_user(row), row["session_id"]

    def revoke_token(self, token: str) -> bool:
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE token_hash = ? AND revoked_at IS NULL",
                (self._now().isoformat(), self._token_hash(token)),
            )
            return cursor.rowcount > 0

    def list_sessions(self, user_id: str, current_session_id: str) -> list[dict[str, Any]]:
        now = self._now()
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            self._cleanup_sessions(connection, now)
            rows = connection.execute(
                """
                SELECT id, created_at, expires_at, last_seen_at, remember_device, user_agent
                FROM auth_sessions
                WHERE user_id = ? AND revoked_at IS NULL
                ORDER BY last_seen_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [
            {
                "id": row["id"], "created_at": row["created_at"],
                "expires_at": row["expires_at"], "last_seen_at": row["last_seen_at"],
                "remember_device": bool(row["remember_device"]),
                "user_agent": row["user_agent"], "current": row["id"] == current_session_id,
            }
            for row in rows
        ]

    def revoke_session(self, user_id: str, session_id: str) -> bool:
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE auth_sessions SET revoked_at = ?
                WHERE id = ? AND user_id = ? AND revoked_at IS NULL
                """,
                (self._now().isoformat(), session_id, user_id),
            )
            return cursor.rowcount > 0

    def revoke_other_sessions(self, user_id: str, current_session_id: str) -> int:
        with sqlite3.connect(self.db_path) as connection:
            cursor = connection.execute(
                """
                UPDATE auth_sessions SET revoked_at = ?
                WHERE user_id = ? AND id != ? AND revoked_at IS NULL
                """,
                (self._now().isoformat(), user_id, current_session_id),
            )
            return cursor.rowcount

    @staticmethod
    def _validate_new_password(password: str) -> None:
        if len(password) < 8:
            raise ValueError("password must be at least 8 characters")

    def change_password(
        self, user_id: str, current_password: str, new_password: str,
        current_session_id: str,
    ) -> None:
        self._validate_new_password(new_password)
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT password_hash FROM users WHERE id = ? AND is_active = 1",
                (user_id,),
            ).fetchone()
            if not row:
                raise ValueError("user not found")
            if not verify_password(current_password, row["password_hash"]):
                raise ValueError("invalid current password")
            now = self._now().isoformat()
            connection.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (hash_password(new_password), now, user_id),
            )
            connection.execute(
                """
                UPDATE auth_sessions SET revoked_at = ?
                WHERE user_id = ? AND id != ? AND revoked_at IS NULL
                """,
                (now, user_id, current_session_id),
            )

    def set_password(self, user_id: str, new_password: str) -> None:
        self._validate_new_password(new_password)
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE")
            if not connection.execute(
                "SELECT 1 FROM users WHERE id = ?", (user_id,)
            ).fetchone():
                raise ValueError("user not found")
            now = self._now().isoformat()
            connection.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (hash_password(new_password), now, user_id),
            )
            connection.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now, user_id),
            )

    def _cleanup_password_reset_tokens(
        self, connection: sqlite3.Connection, now: datetime,
    ) -> None:
        connection.execute(
            "DELETE FROM password_reset_tokens WHERE used_at IS NOT NULL OR expires_at <= ?",
            (now.isoformat(),),
        )

    def create_password_reset_token(self, email: str) -> tuple[str, str] | None:
        now = self._now()
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            self._cleanup_password_reset_tokens(connection, now)
            row = connection.execute(
                "SELECT id FROM users WHERE email = ? AND is_active = 1",
                (self._normalize_email(email),),
            ).fetchone()
            if not row:
                return None
            token = secrets.token_urlsafe(32)
            connection.execute(
                """
                INSERT INTO password_reset_tokens
                (id, user_id, token_hash, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()), row["id"], self._token_hash(token),
                    now.isoformat(), (now + timedelta(hours=1)).isoformat(),
                ),
            )
            return token, row["id"]

    def reset_password(self, token: str, new_password: str) -> str:
        self._validate_new_password(new_password)
        now = self._now()
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup_password_reset_tokens(connection, now)
            row = connection.execute(
                """
                SELECT password_reset_tokens.id AS token_id, password_reset_tokens.user_id
                FROM password_reset_tokens
                JOIN users ON users.id = password_reset_tokens.user_id
                WHERE password_reset_tokens.token_hash = ?
                  AND password_reset_tokens.used_at IS NULL
                  AND password_reset_tokens.expires_at > ?
                  AND users.is_active = 1
                """,
                (self._token_hash(token), now.isoformat()),
            ).fetchone()
            if not row:
                raise ValueError("invalid or expired reset token")
            now_text = now.isoformat()
            connection.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (hash_password(new_password), now_text, row["user_id"]),
            )
            connection.execute(
                "UPDATE auth_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                (now_text, row["user_id"]),
            )
            connection.execute(
                "UPDATE password_reset_tokens SET used_at = ? WHERE id = ?",
                (now_text, row["token_id"]),
            )
            return row["user_id"]

    def list_users(self) -> list[AuthUser]:
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT * FROM users ORDER BY created_at").fetchall()
        return [self._row_to_user(row) for row in rows]

    def set_jellyfin_user_id(
        self, user_id: str, jellyfin_user_id: str | None,
    ) -> AuthUser:
        normalized_id = jellyfin_user_id.strip() if jellyfin_user_id else None
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if not row:
                raise ValueError("user not found")
            try:
                connection.execute(
                    "UPDATE users SET jellyfin_user_id = ?, updated_at = ? WHERE id = ?",
                    (normalized_id, self._now().isoformat(), user_id),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("jellyfin user already linked") from error
            refreshed = connection.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            return self._row_to_user(refreshed)

    def update_user(self, user_id: str, fields: dict[str, object]) -> AuthUser:
        allowed = {"display_name", "email", "role", "is_active"}
        updates = {key: value for key, value in fields.items() if key in allowed}
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                raise ValueError("user not found")
            target_role = updates.get("role", row["role"])
            target_active = bool(updates.get("is_active", row["is_active"]))
            if target_role not in {"admin", "user"}:
                raise ValueError("invalid role")
            if row["role"] == "admin" and row["is_active"] and (target_role != "admin" or not target_active):
                active_admins = connection.execute(
                    "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1"
                ).fetchone()[0]
                if active_admins <= 1:
                    raise ValueError("last administrator cannot be removed")
            if "email" in updates:
                updates["email"] = self._normalize_email(str(updates["email"]))
            if "display_name" in updates:
                updates["display_name"] = str(updates["display_name"]).strip()
            if not updates:
                return self._row_to_user(row)
            updates["updated_at"] = self._now().isoformat()
            clause = ", ".join(f"{key} = ?" for key in updates)
            try:
                connection.execute(
                    f"UPDATE users SET {clause} WHERE id = ?",
                    [*updates.values(), user_id],
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("email already exists") from error
            if not target_active:
                connection.execute(
                    "UPDATE auth_sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
                    (self._now().isoformat(), user_id),
                )
            refreshed = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return self._row_to_user(refreshed)

    def delete_user(self, user_id: str) -> bool:
        with sqlite3.connect(self.db_path) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT role, is_active FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            if not row:
                raise ValueError("user not found")
            if row["role"] == "admin" and row["is_active"]:
                active_admins = connection.execute(
                    "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1"
                ).fetchone()[0]
                if active_admins <= 1:
                    raise ValueError("last administrator cannot be removed")
            connection.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
            cursor = connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return cursor.rowcount > 0
