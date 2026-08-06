# Conservation définitive — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the complete administrator workflow for approving, refusing, or extending temporary film rentals, with permanent storage protection and internal user notifications.

**Architecture:** Extend the existing SQLite rental record with storage policy and decision metadata. Add a small persistent notification table and authenticated API routes, keeping admin routes separate from regular-user routes. Add the admin controls and user notification display to the existing React account/admin surface.

**Tech Stack:** FastAPI, SQLite, Pydantic, React/Vite, existing AuthStore and MediaStore.

## Global Constraints

- Admin downloads are permanent and never create rentals.
- Regular users keep the five-active-rental limit.
- Only `keep_requested` rentals appear in the admin conservation queue.
- Accepted rentals use `status = kept`, `storage_policy = permanent`, and `expires_at = null`.
- Refused rentals return to `available` without deleting files.
- Extensions add seven days to the current expiry.
- Notifications are internal Backstage notifications; no email is added in this slice.
- No automatic or real file deletion is enabled in this slice.
- All timestamps are UTC and all mutating routes require authentication.

---

### Task 1: Persist decisions and notifications

**Files:**
- Modify: `backend/core/models.py`
- Modify: `backend/core/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- `Rental` gains `storage_policy`, `keep_decision`, `decided_by`, and `decided_at`.
- Add `Notification` with `id`, `backstage_user_id`, `kind`, `message`, `read_at`, `created_at`.
- Add store methods `list_keep_requested_rentals`, `decide_rental`, `extend_rental`, `create_notification`, `list_notifications`, and `mark_notification_read`.

- [ ] Write failing store tests for accept/refuse/extend transitions and notification read state.
- [ ] Run the focused store tests and verify they fail because the new columns and methods do not exist.
- [ ] Add additive SQLite migrations, model fields, and transactional store methods.
- [ ] Run the focused store tests and verify they pass.
- [ ] Commit `feat: persist rental decisions and notifications`.

### Task 2: Add administrator decision API

**Files:**
- Modify: `backend/api.py`
- Test: `tests/test_auth_api.py`

**Interfaces:**
- `GET /api/admin/rentals/keep-requests` returns only `keep_requested` rentals with media title and requester display name.
- `POST /api/admin/rentals/{rental_id}/keep` accepts the request, protects the media permanently, and notifies the requester.
- `POST /api/admin/rentals/{rental_id}/refuse` clears the pending request, preserves expiry, and notifies the requester.
- `POST /api/admin/rentals/{rental_id}/extend` adds seven days and notifies the requester.
- `GET /api/notifications` and `POST /api/notifications/{notification_id}/read` are owner-scoped.

- [ ] Write failing API tests for admin access, non-admin denial, ownership isolation, all three decisions, and notifications.
- [ ] Run the focused API tests and verify the expected failures.
- [ ] Implement serializers, admin guards, state validation, and notification creation.
- [ ] Run the focused API tests and verify they pass.
- [ ] Commit `feat: add rental decision API`.

### Task 3: Add admin controls and user notifications

**Files:**
- Modify: `proto-ui/src/api.js`
- Modify: `proto-ui/src/AccountPanel.jsx`
- Modify: `proto-ui/src/BackstagePrototype.jsx`
- Test: `tests/test_catalogue_playback_ui.py`

**Interfaces:**
- Add API helpers for the admin queue, three decisions, notification loading, and marking read.
- Admin account view shows a conservation queue with title, requester, expiry, and the three actions.
- User account view shows unread and recent internal notifications.
- Rental cards show `Conservé définitivement` for `kept` and keep the existing pending label for `keep_requested`.

- [ ] Write failing source-level UI tests for admin action labels, notification helpers, and permanent rental labels.
- [ ] Run the UI tests and verify they fail.
- [ ] Implement the API helpers and UI states using the existing account modal patterns.
- [ ] Run UI tests, lint, and build.
- [ ] Commit `feat: add retention decision interface`.

### Task 4: Full verification and delivery

**Files:**
- Modify: none beyond the task slices
- Test: all existing tests

- [ ] Run the complete Python test suite.
- [ ] Run `npm run lint` and `npm run build` in `proto-ui`.
- [ ] Run `git diff --check` and inspect the final diff.
- [ ] Push `codex/temporary-rentals`, then update `main` and `agent/backstage-docker-deployment`.
- [ ] Deploy through Portainer with Pull and redeploy.
