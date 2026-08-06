# Password Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add self-service password changes, Gmail-backed forgotten-password links, and direct administrator password resets without exposing password data.

**Architecture:** Keep scrypt password hashing in `AuthStore`, add one-time hashed reset tokens in SQLite, and isolate Gmail STARTTLS delivery in a standard-library mail service. Expose public forgot/reset routes, authenticated self-change, and an admin-only password field; extend the existing React authentication gate and account panel without adding a router dependency.

**Tech Stack:** FastAPI, Pydantic, SQLite, Python `hashlib`/`secrets`/`smtplib`/`email`, React, Vite, Docker Compose, pytest.

## Global Constraints

- New passwords must contain at least 8 characters.
- Reset tokens are random, stored only as SHA-256 hashes, single-use, and valid for 1 hour.
- Forgot-password responses must not reveal whether an e-mail exists.
- SMTP secrets must remain in Docker/Portainer environment variables and never enter Git or SQLite.
- Password changes revoke all sessions; self-service keeps only the current session, while admin/reset changes revoke every session.
- Preserve the existing unrelated working-tree changes and stage only files belonging to this feature.
- Use the existing same-origin `/api` client and standard-library SMTP; add no runtime dependency.

---

### Task 1: Add password and reset-token storage primitives

**Files:**
- Modify: `backend/core/auth.py`
- Test: `tests/test_auth_store.py`
- Test: `tests/test_auth_migration.py`

**Interfaces:**
- Produces `AuthStore.change_password(user_id: str, current_password: str, new_password: str, current_session_id: str) -> None`.
- Produces `AuthStore.set_password(user_id: str, new_password: str) -> None`.
- Produces `AuthStore.create_password_reset_token(email: str) -> tuple[str, str] | None`, returning the raw token and user id only for an active matching account.
- Produces `AuthStore.reset_password(token: str, new_password: str) -> str`, returning the affected user id.

- [ ] **Step 1: Write failing store tests for self-service password changes**

Add tests that create an admin, create a second user, authenticate the user twice, then assert that the correct current password changes successfully, the old password no longer authenticates, the new password does authenticate, and the non-current session is revoked while the current session remains valid. Add a test asserting an incorrect current password raises `ValueError("invalid current password")`.

- [ ] **Step 2: Run the focused tests and verify the expected failure**

Run:

```powershell
py -m pytest -q tests/test_auth_store.py -k "change_password or current_password"
```

Expected: FAIL because the new store methods do not exist.

- [ ] **Step 3: Write failing reset-token and admin-reset tests**

Add tests that create a user, create a reset token for its normalized e-mail, verify the token changes the password and invalidates all sessions, verify a second use raises `ValueError("invalid or expired reset token")`, verify an unknown e-mail returns `None`, and verify `set_password` changes the hash and revokes all sessions. Add an expiry test by inserting a token with an `expires_at` in the past and asserting reset is rejected.

- [ ] **Step 4: Run the focused tests and verify the expected failure**

Run:

```powershell
py -m pytest -q tests/test_auth_store.py -k "reset_token or set_password"
```

Expected: FAIL because the reset-token table and methods do not exist.

- [ ] **Step 5: Implement the additive schema and minimal store methods**

In `init_schema`, create:

```sql
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
)
```

Add an index on `(user_id, expires_at)`. Use `hash_password` for all new passwords, `verify_password` for the current password, `_token_hash` for reset tokens, `secrets.token_urlsafe(32)` for raw tokens, and `BEGIN IMMEDIATE` when consuming a reset token. Delete expired/used tokens before creating or consuming tokens. Keep the current session only in `change_password`; revoke every session in `set_password` and `reset_password`.

- [ ] **Step 6: Run the store and migration tests**

Run:

```powershell
py -m pytest -q tests/test_auth_store.py tests/test_auth_migration.py
```

Expected: PASS, including all existing authentication tests.

- [ ] **Step 7: Commit the storage slice**

```powershell
git add -- backend/core/auth.py tests/test_auth_store.py tests/test_auth_migration.py
git commit -m "feat: add password reset storage"
```

### Task 2: Add Gmail SMTP configuration and delivery

**Files:**
- Create: `backend/core/email.py`
- Modify: `backend/config.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example` while preserving its existing user changes
- Test: `tests/test_email.py`

**Interfaces:**
- Produces `EmailSender.send_password_reset(recipient: str, reset_url: str) -> None`.
- `EmailSender` reads `Config.SMTP_HOST`, `Config.SMTP_PORT`, `Config.SMTP_USERNAME`, `Config.SMTP_PASSWORD`, and `Config.SMTP_FROM`.

- [ ] **Step 1: Write a failing e-mail sender test**

Test that a configured sender creates a plain-text message with subject `Réinitialisation de votre mot de passe Backstage`, the recipient, sender, and reset URL, then connects with `smtplib.SMTP(host, port)`, calls `starttls()`, `login(username, password)`, and `send_message(message)`. Use a small fake SMTP object injected through a constructor factory so the test never contacts Gmail. Add a test that missing SMTP credentials raises `RuntimeError("SMTP non configuré")` before connecting.

- [ ] **Step 2: Run the e-mail test and verify it fails**

Run:

```powershell
py -m pytest -q tests/test_email.py
```

Expected: FAIL because `backend/core/email.py` does not exist.

- [ ] **Step 3: Implement the standard-library sender**

Create `EmailSender` with an optional `smtp_factory` defaulting to `smtplib.SMTP`. Build an `EmailMessage`, set `From`, `To`, and `Subject`, set a concise French body containing the reset URL and one-hour validity, use a context manager or guaranteed `quit()`, and perform STARTTLS before login. Treat an empty username/password/from value as disabled configuration and raise the documented runtime error.

- [ ] **Step 4: Add configuration variables without committing secrets**

Add these `Config` values with safe empty defaults:

```python
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM")
BACKSTAGE_PUBLIC_URL = os.getenv("BACKSTAGE_PUBLIC_URL", "http://localhost:8090")
```

Pass the same variables through `docker-compose.yml` and document their names, Gmail’s `smtp.gmail.com:587`, and the requirement for a Google app password in `.env.example`. Do not add a real address or credential.

- [ ] **Step 5: Run the e-mail tests**

Run:

```powershell
py -m pytest -q tests/test_email.py
```

Expected: PASS.

- [ ] **Step 6: Commit the mail slice**

Stage only the new sender and the intended configuration hunks, then run:

```powershell
git commit -m "feat: add Gmail password reset mailer"
```

### Task 3: Expose password-management API routes

**Files:**
- Modify: `backend/auth_api.py`
- Modify: `tests/test_auth_api.py`

**Interfaces:**
- Adds `POST /api/auth/change-password` with `current_password`, `new_password`, `password_confirmation`.
- Adds `POST /api/auth/forgot-password` with `email`, returning `202` and `{"message": "Si un compte correspond, un e-mail vient d'être envoyé."}`.
- Adds `POST /api/auth/reset-password` with `token`, `new_password`, `password_confirmation`.
- Extends `PATCH /api/auth/users/{user_id}` with an optional admin-only `password` field.

- [ ] **Step 1: Write failing API tests**

Add tests covering: authenticated self-change succeeds and preserves the current cookie; incorrect current password returns `422`; mismatched confirmation returns `422`; forgot-password returns the same `202` response for a known and unknown e-mail; a known e-mail invokes the sender with a URL containing `BACKSTAGE_PUBLIC_URL` and the raw token; reset succeeds and consumes the token; an admin can set another user’s password; and a standard user receives `403` when attempting the admin password field. Inject a fake `EmailSender` through the route dependency or module factory.

- [ ] **Step 2: Run the API tests and verify the expected failure**

Run:

```powershell
py -m pytest -q tests/test_auth_api.py -k "password"
```

Expected: FAIL because the request models and routes do not exist.

- [ ] **Step 3: Implement request models and validation**

Add `PasswordChangeRequest`, `ForgotPasswordRequest`, and `PasswordResetRequest`, each requiring a new password of at least 8 characters where applicable. Reject mismatched confirmations before touching the database. Keep the existing `_handle_store_error` mapping and return generic forgot-password output for every valid-looking e-mail.

- [ ] **Step 4: Implement the authenticated and admin routes**

Call `store.change_password` for the current user and current session. For admin updates, remove `password` from the public user update dictionary, call `store.set_password` separately, and return only the sanitized user. Do not allow the password field to be used by standard users because the route remains behind `require_admin`.

- [ ] **Step 5: Implement forgot/reset delivery**

On forgot, call `create_password_reset_token`; if it returns a target, construct `f"{Config.BACKSTAGE_PUBLIC_URL.rstrip('/')}/reset-password?token={quote(token)}"` and call `EmailSender().send_password_reset`. Return the same `202` even when SMTP is disabled or the address is unknown, while logging the delivery failure server-side without including the password or raw token. On reset, call `store.reset_password` and map invalid/expired tokens to `400`.

- [ ] **Step 6: Run the API tests**

Run:

```powershell
py -m pytest -q tests/test_auth_api.py
```

Expected: PASS.

- [ ] **Step 7: Commit the API slice**

```powershell
git add -- backend/auth_api.py tests/test_auth_api.py
git commit -m "feat: add password management API"
```

### Task 4: Add login, account, and reset UI flows

**Files:**
- Create: `proto-ui/src/PasswordResetPage.jsx`
- Modify: `proto-ui/src/api.js`
- Modify: `proto-ui/src/AuthGate.jsx`
- Modify: `proto-ui/src/AccountPanel.jsx`
- Modify: `proto-ui/src/App.css` only if new auth styling is needed

**Interfaces:**
- `requestPasswordReset(email) -> Promise<{message: string}>`.
- `resetPassword(payload) -> Promise<{message: string}>`.
- `changePassword(payload) -> Promise<{message: string}>`.
- `updateUser(userId, {password})` is used only by the admin panel.

- [ ] **Step 1: Add failing frontend behavior checks**

Use the project’s available lint/build checks as the executable frontend gate. First add the API exports and UI components with intentionally referenced behavior, then run the lint command and verify it reports the missing imports/exports. Keep all forms accessible with labels, `type="password"`, `minLength={8}`, and `autoComplete` values.

- [ ] **Step 2: Add API client functions**

Add same-origin JSON calls for the three new public/authenticated endpoints. Preserve the existing `authRequest` error behavior and add a small public JSON helper only if needed for forgot/reset routes.

- [ ] **Step 3: Add forgotten-password mode to `AuthGate`**

Add a **Mot de passe oublié ?** link to the login form, a forgot form with generic success copy, and a return-to-login action. Detect `window.location.pathname === '/reset-password'` before the normal authenticated gate and render `PasswordResetPage` with `new URLSearchParams(window.location.search).get('token')`. After a successful reset, return to login without authenticating automatically.

- [ ] **Step 4: Add the reset page**

Render new password and confirmation fields, submit `resetPassword`, show invalid/expired-token errors, and show a success message with a login link. Never display or persist the token outside the URL and request payload.

- [ ] **Step 5: Add self-service password form to `AccountPanel`**

Add a **Changer mon mot de passe** section with current/new/confirmation fields. On success, clear all fields, refresh devices, and show a confirmation. The current session remains valid while other remembered devices are logged out.

- [ ] **Step 6: Add admin direct reset form**

For each user row, add a password input and an explicit **Définir** button. Call `updateUser(target.id, {password})`, clear only that row’s input after success, and show the result. Never preload or display any existing password.

- [ ] **Step 7: Run frontend checks**

Run:

```powershell
npm --prefix proto-ui run lint
npm --prefix proto-ui run build
```

Expected: both commands exit with code 0.

- [ ] **Step 8: Commit the UI slice**

```powershell
git add -- proto-ui/src/api.js proto-ui/src/AuthGate.jsx proto-ui/src/PasswordResetPage.jsx proto-ui/src/AccountPanel.jsx proto-ui/src/App.css
git commit -m "feat: add password recovery UI"
```

### Task 5: Full verification and deployment handoff

**Files:**
- Modify: `docs/backstage-authentication.md`
- Modify: `README.md`
- Test: all existing test files

- [ ] **Step 1: Document Gmail setup and Portainer variables**

Document Google two-step verification, creation of a Google app password, the six environment variables, and the fact that `SMTP_PASSWORD` is entered in Portainer’s stack environment rather than committed to Git. Document the public reset URL as `https://backstage.home.arpa/reset-password`.

- [ ] **Step 2: Run the complete verification suite**

Run:

```powershell
py -m pytest -q
npm --prefix proto-ui run lint
npm --prefix proto-ui run build
docker compose config --quiet
```

Expected: all Python tests pass, lint and build exit 0, and Compose configuration validates.

- [ ] **Step 3: Review the final diff and working tree**

Run:

```powershell
git diff --check HEAD~4..HEAD
git status --short --branch
```

Confirm that only password-management commits contain feature files and that unrelated existing modifications remain unstaged.

- [ ] **Step 4: Commit documentation**

```powershell
git add -- docs/backstage-authentication.md README.md
git commit -m "docs: document password recovery setup"
```

- [ ] **Step 5: Push and deploy**

Push `agent/backstage-docker-deployment`, then in Portainer pull and redeploy the stack from that branch. Enter the Gmail SMTP variables in the stack environment, deploy, and test the flow with a non-admin account. Do not paste the Gmail app password into chat.
