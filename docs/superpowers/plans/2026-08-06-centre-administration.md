# Centre d’administration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give administrators one central place for server activity, rentals, storage, users, services, and settings without mixing those controls into the account panel or library.

**Architecture:** Reuse the existing admin APIs, extract the aggregation logic from `/admin/dashboard` into a pure backend helper, and add an `AdminCenter` React surface opened from an administrator-only navigation entry. `AccountPanel` keeps personal account settings and notifications; administration moves to the new surface.

**Tech Stack:** FastAPI, SQLite, Pydantic, React 19, Vite, Tailwind CSS, existing Radarr/Sonarr/Seerr/Jellyfin clients.

## Global Constraints

- Administration is visible only to users with the `admin` role.
- The Centre d’administration contains Vue d’ensemble, Activité serveur, Demandes et locations, Conservation définitive, Utilisateurs et droits, Stockage et quotas, Services, and Paramètres.
- No routine administrative action should require a command line.
- Backup controls are not part of the immediate implementation; they remain deferred until the dedicated disk is available.
- The visual direction is centered, modern, cinematic, and restrained.

---

### Task 1: Extract and test the admin dashboard aggregation

**Files:**
- Create: `backend/core/admin_dashboard.py`
- Modify: `backend/api.py:731-779`
- Create: `tests/test_admin_dashboard.py`

**Interfaces:**
- Consumes: media-server activity items, rental rows, user rows, storage status, and a UTC `datetime`.
- Produces:

```python
def build_admin_dashboard(
    *,
    activity: dict[str, Any],
    rentals: list[dict[str, Any]],
    users: list[dict[str, Any]],
    storage: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    """Build the admin dashboard payload without I/O."""
```

- [ ] **Step 1: Write failing unit tests for the pure helper.** Cover downloads (`requested`, `searching`, `downloading`), errors (`error` or `last_error`), rentals expiring within three days, non-admin quota exclusion, service/storage passthrough, and inclusion of the full activity list for the activity tab.

```python
def test_build_admin_dashboard_groups_activity_and_expiring_rentals():
    now = datetime(2026, 8, 6, tzinfo=timezone.utc)
    result = build_admin_dashboard(
        activity={"items": [
            {"media_id": "a", "state": "downloading"},
            {"media_id": "b", "state": "error", "last_error": "timeout"},
        ]},
        rentals=[{
            "media_title": "Dune",
            "rental": Rental(
                id="r1", media_id="a", backstage_user_id="u1",
                requested_at=now, expires_at=now + timedelta(days=1),
                created_at=now, updated_at=now,
            ),
        }],
        users=[{"id": "u1", "display_name": "Paul", "role": "user"}],
        storage={"temporary_gb": 4},
        now=now,
    )
    assert [item["media_id"] for item in result["downloads"]] == ["a"]
    assert [item["media_id"] for item in result["errors"]] == ["b"]
    assert result["expiring"][0]["requester_name"] == "Paul"
```

- [ ] **Step 2: Run `pytest tests/test_admin_dashboard.py -q` and confirm the new tests fail because the helper does not exist.**
- [ ] **Step 3: Implement `build_admin_dashboard` with deterministic filtering and stable keys:** `activity`, `expiring`, `downloads`, `errors`, `services`, `storage`, and `quotas`.
- [ ] **Step 4: Change `/admin/dashboard` to gather dependencies and delegate all shaping to the helper.** Keep `require_admin` on the route and pass the full activity payload through.
- [ ] **Step 5: Run `pytest tests/test_admin_dashboard.py tests/test_api.py -q` and confirm the tests pass.**
- [ ] **Step 6: Commit the backend aggregation.**

```bash
git add backend/core/admin_dashboard.py backend/api.py tests/test_admin_dashboard.py
git commit -m "feat(admin): expose tested dashboard aggregation"
```

### Task 2: Add the centralized admin API client surface

**Files:**
- Modify: `proto-ui/src/api.js:180-280`
- Create: `proto-ui/src/adminApi.js`
- Test: `proto-ui` lint and build

**Interfaces:**
- Consumes: `/admin/dashboard`, `/media-server/activity`, `/admin/rentals/keep-requests`, `/admin/rentals/cleanup-preview`, `/admin/storage/status`, `/media-server/status`, and existing user endpoints.
- Produces:

```js
export async function fetchAdminCenterData() {
    const [dashboard, activity, keepRequests, cleanupPreview, services, users] = await Promise.all([
        fetchAdminDashboard(),
        fetchMediaServerActivity(),
        fetchKeepRequests(),
        fetchCleanupPreview(),
        fetchMediaServerStatus(),
        fetchUsers(),
    ]);
    return {dashboard, activity, keepRequests, cleanupPreview, services, users};
}
```

- [ ] **Step 1: Add an API error helper that preserves the server `detail` message and distinguishes `403` from service failures.**
- [ ] **Step 2: Implement `fetchAdminCenterData` with `Promise.all`.** Do not include backup endpoints in this initial aggregate.
- [ ] **Step 3: Keep existing endpoint functions as named exports for current callers.** `AccountPanel` and the activity modal must not break during the transition.
- [ ] **Step 4: Run `npm run lint` and `npm run build`.**
- [ ] **Step 5: Commit the client aggregation.**

```bash
git add proto-ui/src/api.js proto-ui/src/adminApi.js
git commit -m "feat(admin): aggregate admin center data"
```

### Task 3: Build the Administrator Center

**Files:**
- Create: `proto-ui/src/components/AdminCenter.jsx`
- Modify: `proto-ui/src/BackstagePrototype.jsx`
- Modify: `proto-ui/src/AccountPanel.jsx`
- Modify: `proto-ui/src/App.css`
- Test: `proto-ui` lint and build plus manual admin acceptance

**Interfaces:**
- Consumes: `fetchAdminCenterData`, existing retention action functions, user functions, and service sync/import functions.
- Produces:

```jsx
<AdminCenter
    isDarkMode={isDarkMode}
    onClose={() => setShowAdminCenter(false)}
    onOpenMedia={(mediaId) => openMediaById(mediaId)}
/>
```

- [ ] **Step 1: Add an administrator-only `Administration` entry to the main navigation.** Do not render the entry when `user.role !== 'admin'`.
- [ ] **Step 2: Create the centered `AdminCenter` surface with a local section state:** `overview`, `activity`, `requests`, `users`, `storage`, `services`, and `settings`.
- [ ] **Step 3: Render Overview cards for expiring rentals, active downloads, errors, free storage, temporary storage, and users near quota.** Use explicit loading, empty, and error states.
- [ ] **Step 4: Render Activity with server items, progress, provider, path/disk information, errors, refresh, sync, and import actions.** Keep technical details inside the admin surface.
- [ ] **Step 5: Move retention requests, cleanup preview, storage/quota information, service status, and user/Jellyfin management from the account panel into their corresponding admin sections.** Keep the existing action functions and refresh after mutations.
- [ ] **Step 6: Leave personal name, password, devices, and notifications in `AccountPanel`.** Remove only the duplicate admin sections and keep the panel usable for every user.
- [ ] **Step 7: Keep backup UI out of the new center for now.** Do not add new backup behavior; the existing backup controls remain untouched until the dedicated disk is available.
- [ ] **Step 8: Make the admin surface centered and responsive, with a persistent section navigation on desktop and a compact selector on mobile.**
- [ ] **Step 9: Run `npm run lint` and `npm run build`.**
- [ ] **Step 10: Manually verify admin and normal-user permissions, refresh behavior, empty states, service failures, retention actions, and activity import/sync.**
- [ ] **Step 11: Commit the Admin Center.**

```bash
git add proto-ui/src/components/AdminCenter.jsx proto-ui/src/BackstagePrototype.jsx proto-ui/src/AccountPanel.jsx proto-ui/src/App.css
git commit -m "feat(ui): add centralized admin center"
```

### Verification checklist

- Admin users see one Administration entry and one centered admin surface.
- Normal users cannot see or call admin UI actions; the backend still returns `403` for protected routes.
- Activity server, downloads, errors, storage, quotas, users, services, rentals, and conservation requests are reachable from the same center.
- Account settings remain separate from administration.
- Backup controls remain deferred.
- `pytest -q` and `npm run lint && npm run build` pass.
