# Backstage Authentication and Roles Design

## Goal

Add a first-run administrator setup, browser login/logout, persistent sessions, a 30-day “remember this device” option, and the initial `admin`/`user` roles without changing the existing shared media catalog.

## Scope

This phase covers authentication and authorization only. It does not yet add per-user watchlists, Jellyfin account linking, Seerr requests, temporary rentals, or notifications. Those phases will consume the authenticated user identity introduced here.

## Current context

- FastAPI routes are exposed under `/api` from `backend/api.py`.
- `MediaStore` owns the SQLite schema initialization in `backend/core/store.py`.
- The existing `media`, `episode`, and `media_availability` tables must remain unchanged in meaning and data.
- The React frontend is served by the same FastAPI process and calls relative `/api` URLs.
- The Docker deployment persists the SQLite file at `/srv/data/backstage/backstage.db` on the server.

## Chosen approach

Use same-origin, cookie-based sessions backed by SQLite. The browser receives only a random opaque session token; the database stores a SHA-256 digest of that token. Passwords are hashed with Python’s standard-library `hashlib.scrypt` using a per-password random salt. This avoids putting credentials in Portainer environment variables and avoids adding a password-hashing dependency.

The frontend will use an `HttpOnly` cookie and will never read or store the session token in JavaScript. `SameSite=Lax` will be used. The `Secure` flag will be enabled when Backstage is configured for HTTPS and disabled for the current local HTTP deployment so the login works at `http://192.168.1.5:8090`.

## First-run setup

`GET /api/auth/status` reports whether an administrator exists and whether setup is required.

When no administrator exists, the frontend displays a setup screen with:

- display name;
- email address;
- password;
- password confirmation.

`POST /api/auth/setup` creates exactly one administrator inside a SQLite transaction. It rejects the request once an administrator already exists. The endpoint validates a non-empty display name, a normalized email address, and a password of at least 8 characters. After successful setup, the endpoint creates a normal authenticated session and returns the new user profile.

The setup screen must not be reachable after the first administrator has been created, even if a user revisits the URL.

## Database schema

`AuthStore.init_schema()` will create the following tables with `CREATE TABLE IF NOT EXISTS`; `main.py` will call it alongside `MediaStore.init_schema()`. This is an additive migration and will not rewrite existing media rows.

```sql
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

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
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_user
    ON auth_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_sessions_expiry
    ON auth_sessions(expires_at);
```

The imported `backstage.db` remains valid because these tables are added only when the application starts. A future database migration system may replace this lightweight initialization once the schema becomes more complex.

## Session behavior

- A normal login session expires when the browser session ends or after 24 hours, whichever comes first.
- With “Se souvenir de cet appareil”, the session expires after 30 days.
- The cookie value is generated with `secrets.token_urlsafe(32)`.
- Only `sha256(cookie_value)` is stored in SQLite.
- Every authenticated request verifies that the session exists, is not revoked, belongs to an active user, and has not expired.
- `last_seen_at` is refreshed during authentication.
- Logout sets `revoked_at` and clears the browser cookie.
- Expired and revoked sessions are removed opportunistically during login and through an admin/device-list request.

The initial device-management endpoint lists the current user’s sessions using safe metadata only: creation date, last activity, approximate device/user-agent label, expiration date, and whether the session is current. It supports revoking a selected session and revoking all other sessions.

## User administration

After setup, an administrator can create regular users from the Backstage account area. The first implementation accepts display name, email, and an initial password of at least 8 characters, and always creates the account with the `user` role. An administrator can rename, deactivate, reactivate, promote/demote, or permanently delete an account, but cannot delete their own account and cannot remove the last active administrator. Deactivating or deleting a user revokes all of that user’s sessions.

## API surface

The authentication router will be included under the existing `/api` prefix:

- `GET /api/auth/status` — returns `{ "setup_required": boolean }`.
- `POST /api/auth/setup` — creates the first admin and signs in.
- `POST /api/auth/login` — accepts email, password, and `remember_device`; signs in on success.
- `POST /api/auth/logout` — revokes the current session and clears the cookie.
- `GET /api/auth/me` — returns the authenticated user profile or `401`.
- `GET /api/auth/devices` — returns the current user’s active sessions or `401`.
- `DELETE /api/auth/devices/{session_id}` — revokes one session owned by the current user.
- `POST /api/auth/devices/revoke-others` — revokes all current-user sessions except the current one.
- `GET /api/auth/users` — returns the user list for administrators.
- `POST /api/auth/users` — creates a regular user for administrators.
- `PATCH /api/auth/users/{user_id}` — updates display name, role, or active state for administrators.
- `DELETE /api/auth/users/{user_id}` — permanently deletes another user for administrators.

Authentication dependencies will provide `get_current_user` and `require_admin`. Existing media and maintenance routes will be protected by `get_current_user` in this phase. Administrative-only routes will use `require_admin`; initially this applies to media-server import, synchronization, and acquisition actions that can modify external services. Read-only catalog and playback routes remain available to authenticated users.

## Frontend behavior

The React app will perform the following bootstrap sequence:

1. Request `/api/auth/status`.
2. Show setup if `setup_required` is true.
3. Otherwise request `/api/auth/me`.
4. Show login if the response is `401`.
5. Render the existing application when a user is authenticated.

The login form includes the “Se souvenir de cet appareil” checkbox. A `401` from any API request will clear the in-memory user state and return the user to login. The existing media API functions will use `credentials: 'same-origin'` so the session cookie is sent on every request.

The first implementation will use a minimal auth screen matching the current application style. Device management will be reachable from a small account/admin menu after login; it will not introduce a separate design system.

The admin account area will include a compact user list with create, edit, activate/deactivate, and role controls. It will prevent the last active administrator from being removed or demoted and will show the resulting API error in the interface.

## Security and error handling

- Authentication errors use a generic “identifiants invalides” message and do not reveal whether an email exists.
- Inactive users receive `403` after valid session lookup.
- Duplicate email and second setup attempts return `409`.
- Missing or malformed cookies behave as unauthenticated requests.
- Password hashes, session tokens, and raw cookies are never logged.
- Mutating authenticated endpoints validate the `Origin` header when present and require same-origin requests; this complements the `HttpOnly` cookie for the local deployment.
- CORS will not be used to grant cross-origin credential access to the auth API.

## Testing strategy

Backend tests will cover:

- setup creates one admin and an authenticated session;
- a second setup attempt is rejected;
- valid login succeeds;
- invalid credentials return a generic `401`;
- a normal session and a remembered session receive the correct expiry behavior;
- logout revokes the session;
- expired and revoked sessions are rejected;
- inactive users cannot authenticate;
- a regular user cannot access an admin-protected route;
- a user can revoke only their own device sessions;
- existing media rows remain readable after auth tables are initialized.

Frontend tests/build verification will cover the bootstrap states (setup, login, authenticated) through the existing lint and production build checks. The deployment verification will start from the imported database, confirm the new auth tables are additive, and verify that a Portainer redeploy leaves the media rows intact.

## Success criteria

The phase is complete when:

1. A fresh database shows the setup screen and can create the first admin.
2. A second setup attempt is impossible.
3. An authenticated user can use the existing catalog and playback routes.
4. A remembered device remains signed in for 30 days unless revoked.
5. A regular user cannot call admin-protected actions.
6. The existing 252 media rows and 1091 episode rows remain available after migration and redeployment.
