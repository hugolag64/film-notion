# Bibliothèque nettoyée Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In the Films library, show only server-ready films in the grid, move tracked-but-not-ready films into an « En route » row with one colored badge each, replace the support pills with a personal rental badge, and add a « Mes locations » filter.

**Architecture:** One small backend change makes per-film download state readable by every flatmate (`GET /api/library/available` gains a `states` map). Badge and placement rules live as pure functions in `library.js` / `rentals.js`, unit-tested with `node --test`. `BackstagePrototype.jsx` only wires them in.

**Tech Stack:** FastAPI + pytest (backend), React 19 + Vite + Tailwind 4, `node --test` (frontend).

**Spec:** `docs/superpowers/specs/2026-11-26-bibliotheque-nettoyee-design.md`

## Global Constraints

- All user-facing copy in French, exactly: « En route », « Mes locations », « Sort le JJ/MM », « Au cinéma », « Demandé », « Recherche », « Téléchargement NN % », « Erreur », « Bientôt prêt », « Ta location · J-x », « Gardé ».
- « Au cinéma » window: release date less than 4 months ago → constant `CINEMA_WINDOW_DAYS = 120`.
- « Sur le serveur » = ready on Jellyfin (`jellyfin_id` set): same rule as the existing « ▶ Disponible maintenant » filter.
- The split grid / En route applies to the **Films** collection only. Séries keep today's behavior (except that the support pills disappear everywhere).
- Do not expose `last_error`, `root_folder`, `arr_id` or profile ids to non-admins.
- Work on a branch, never on `main`.

## Review Focus

1. A non-admin flatmate opens Films → they must see the En route row (data comes from `/library/available`, not the admin-only activity endpoint). Pinned in Task 1.
2. A requested film with no release date → « Demandé », never a crash or « Sort le NaN ». Pinned in Task 2.
3. A downloading film whose progress is unknown (`progress_percent: null`) → « Téléchargement », not « Téléchargement null % ». Pinned in Task 2.
4. A film released today → « Au cinéma », not « Sort le … » (date compared as local calendar days, not UTC instants). Pinned in Task 2.
5. An expired or cancelled rental must not keep a film under « Mes locations » nor show « Ta location ». Pinned in Task 3.

---

### Task 1: Expose per-film states to every flatmate

**Files:**
- Modify: `backend/api.py:593-599` (`list_available_media`)
- Test: `tests/test_coloc_rentals.py` (next to `test_library_available_lists_only_media_ready_on_jellyfin`)

**Interfaces:**
- Produces: `GET /api/library/available` → `{"media_ids": [str], "states": {media_id: {"state": AvailabilityState, "progress_percent": int | None, "ready": bool}}}`. `media_ids` unchanged (Jellyfin-ready ids). `states` holds every availability row; `ready` = `jellyfin_id` is set.

- [ ] **Step 1: Write the failing test** `test_library_available_shares_download_states_with_flatmates`, same setup as the existing test (non-admin login, `ready` available with `jf-1`, `pending` downloading) plus `pending` with `progress_percent=42` and `last_error="boom"`:

```python
body = client.get("/api/library/available").json()
assert body["media_ids"] == ["ready"]
assert body["states"] == {
    "ready": {"state": "available", "progress_percent": None, "ready": True},
    "pending": {"state": "downloading", "progress_percent": 42, "ready": False},
}
assert "boom" not in json.dumps(body)
```

- [ ] **Step 2: Run** `python -m pytest tests/test_coloc_rentals.py -k library_available -v` → new test FAILS (`KeyError: 'states'`), old one passes.
- [ ] **Step 3: Implement** in `list_available_media`: fetch `store.list_availabilities()` once, build both keys from it with only the three listed fields.
- [ ] **Step 4: Run** the same command → both PASS; then `python -m pytest -q` → all green.
- [ ] **Step 5: Commit** `git commit -m "Partage l'état de téléchargement des films avec les colocs"`

### Task 2: Placement and En route badge rules

**Files:**
- Modify: `proto-ui/src/library.js` (append)
- Test: `proto-ui/src/library.test.js` (append)

**Interfaces:**
- Consumes: the `states` entry shape from Task 1.
- Produces:
  - `export const CINEMA_WINDOW_DAYS = 120`
  - `export function libraryPlacement(mediaId: string, states: Record<string, {state, progress_percent, ready}>): 'grid' | 'enRoute'`: `'grid'` when no entry or `entry.ready`, `'enRoute'` otherwise.
  - `export function enRouteBadge(releaseDate: string | null, entry: {state, progress_percent}, now: Date = new Date()): {label: string, tone: 'cinema' | 'upcoming' | 'requested' | 'searching' | 'downloading' | 'error'}`

Rules for `enRouteBadge`:
- `downloading` → `Téléchargement ${p} %` (tone `downloading`); `Téléchargement` when `p` is null.
- `searching` → `Recherche` / `searching`. `error` → `Erreur` / `error`. `available` or `imported` → `Bientôt prêt` / `downloading`.
- `requested` (or any other state): compare `releaseDate` (`YYYY-MM-DD`, first 10 chars) to `now` as a **local** `YYYY-MM-DD` string. Later than today → `Sort le DD/MM` / `upcoming`. Otherwise, if the gap in days is `< CINEMA_WINDOW_DAYS` → `Au cinéma` / `cinema`. Otherwise, or when there is no date → `Demandé` / `requested`. Compute the gap from `Date.UTC(y, m-1, d)` values of the two calendar dates.

- [ ] **Step 1: Write the failing tests** (`now = new Date(2026, 10, 26)`):

```js
test('placement: ready or untracked media stay in the grid', () => {
    const states = { a: { state: 'available', ready: true }, b: { state: 'downloading', ready: false } };
    assert.equal(libraryPlacement('a', states), 'grid');
    assert.equal(libraryPlacement('z', states), 'grid');
    assert.equal(libraryPlacement('b', states), 'enRoute');
});
test('badge: requested films use the release date', () => {
    const req = { state: 'requested' };
    assert.deepEqual(enRouteBadge('2027-03-12', req, now), { label: 'Sort le 12/03', tone: 'upcoming' });
    assert.deepEqual(enRouteBadge('2026-11-26', req, now), { label: 'Au cinéma', tone: 'cinema' });
    assert.deepEqual(enRouteBadge('2026-08-01', req, now), { label: 'Au cinéma', tone: 'cinema' });
    assert.deepEqual(enRouteBadge('2026-07-01', req, now), { label: 'Demandé', tone: 'requested' });
    assert.deepEqual(enRouteBadge(null, req, now), { label: 'Demandé', tone: 'requested' });
});
test('badge: live download states', () => {
    assert.equal(enRouteBadge(null, { state: 'downloading', progress_percent: 42 }, now).label, 'Téléchargement 42 %');
    assert.equal(enRouteBadge(null, { state: 'downloading', progress_percent: null }, now).label, 'Téléchargement');
    assert.equal(enRouteBadge(null, { state: 'searching' }, now).label, 'Recherche');
    assert.equal(enRouteBadge(null, { state: 'error' }, now).label, 'Erreur');
    assert.equal(enRouteBadge(null, { state: 'imported' }, now).label, 'Bientôt prêt');
});
```

- [ ] **Step 2: Run** `npm test` in `proto-ui` → FAIL (`libraryPlacement` is not exported).
- [ ] **Step 3: Implement** both functions in `library.js`.
- [ ] **Step 4: Run** `npm test` → PASS.
- [ ] **Step 5: Commit** `git commit -m "Ajoute les règles de la rangée En route"`

### Task 3: Personal rental badge and « Mes locations » predicate

**Files:**
- Modify: `proto-ui/src/rentals.js` (append)
- Create: `proto-ui/src/rentals.test.js`
- Modify: `proto-ui/package.json` (`test` script also runs `src/rentals.test.js`)

**Interfaces:**
- Produces:
  - `export const isOpenRental = (rental) => boolean`: true when the status is set and not `expired` or `cancelled`.
  - `export const rentalCardBadge = (rental, now = new Date()) => {label, tone: 'rental' | 'kept'} | null`:
    - `kept` or `keep_requested` → `Gardé` / `kept`.
    - `available` → `Ta location · J-${days}` / `rental`, with `days = max(0, ceil((expires_at - now) / 86_400_000))`. Plain `Ta location` when there is no `expires_at`.
    - Anything else, including null → `null`.

- [ ] **Step 1: Write the failing tests** (`now = new Date('2026-11-26T12:00:00Z')`):

```js
assert.equal(isOpenRental({ status: 'available' }), true);
assert.equal(isOpenRental({ status: 'requested' }), true);
assert.equal(isOpenRental({ status: 'expired' }), false);
assert.equal(isOpenRental({ status: 'cancelled' }), false);
assert.equal(isOpenRental(null), false);
assert.deepEqual(rentalCardBadge({ status: 'available', expires_at: '2026-12-01T12:00:00Z' }, now), { label: 'Ta location · J-5', tone: 'rental' });
assert.deepEqual(rentalCardBadge({ status: 'available', expires_at: '2026-11-20T12:00:00Z' }, now), { label: 'Ta location · J-0', tone: 'rental' });
assert.deepEqual(rentalCardBadge({ status: 'available' }, now), { label: 'Ta location', tone: 'rental' });
assert.deepEqual(rentalCardBadge({ status: 'kept' }, now), { label: 'Gardé', tone: 'kept' });
assert.equal(rentalCardBadge({ status: 'expired', expires_at: '2026-12-01T12:00:00Z' }, now), null);
assert.equal(rentalCardBadge(undefined, now), null);
```

- [ ] **Step 2: Run** `npm test` → FAIL.
- [ ] **Step 3: Implement** both functions in `rentals.js` and update the `test` script.
- [ ] **Step 4: Run** `npm test` → PASS.
- [ ] **Step 5: Commit** `git commit -m "Ajoute le badge de location personnelle"`

### Task 4: Wire it into the library view

**Files:**
- Modify: `proto-ui/src/api.js:424-428`
- Modify: `proto-ui/src/BackstagePrototype.jsx`: imports (l.13, l.20), `mapMediaToMovie` (~l.150), state (~l.232), `refreshAvailableMediaIds` (~l.719), filtering and pagination (~l.868-877), filter chips (~l.1732), cards (~l.1756-1794).

**Interfaces:**
- Consumes: Task 1 response, `libraryPlacement` / `enRouteBadge` (Task 2), `isOpenRental` / `rentalCardBadge` (Task 3).
- Produces: `export async function fetchLibraryAvailability(): Promise<{mediaIds: string[], states: Record<string, {state, progress_percent, ready}>}>`, which replaces `fetchAvailableMediaIds` (its only caller is `refreshAvailableMediaIds`).

- [ ] **Step 1:** In `api.js`, replace `fetchAvailableMediaIds` with `fetchLibraryAvailability`, which returns `{mediaIds: body.media_ids || [], states: body.states || {}}`. In `BackstagePrototype.jsx`, add `const [libraryStates, setLibraryStates] = useState({})` and have `refreshAvailableMediaIds` set both `availableMediaIds` and `libraryStates`. Add `releaseDate: media.release_date || null` to `mapMediaToMovie`.
- [ ] **Step 2:** Add `const [onlyMine, setOnlyMine] = useState(false)`. Add the filter `.filter((movie) => !onlyMine || isOpenRental(rentalsByMedia[movie.id]))` after the `onlyAvailable` filter, and add `onlyMine` to `libraryKey`. Split `filteredMovies`:
  - Films collection: `enRouteMovies` = the items whose `libraryPlacement(movie.id, libraryStates) === 'enRoute'`; `gridMovies` = the rest.
  - Séries: `enRouteMovies = []` and `gridMovies = filteredMovies`.
  - Pagination (`visibleMovies`, « N sur M »), the « Titres affichés » count and the empty state all use `gridMovies`.
- [ ] **Step 3:** Next to « ▶ Disponible maintenant », add a « Mes locations » toggle with the same markup and `aria-pressed={onlyMine}`, in `#635bff` instead of emerald.
- [ ] **Step 4:** Remove the support pills block and the admin `availabilityByMedia[movie.id]` pill from the cards. Render `rentalCardBadge(rentalsByMedia[movie.id])` instead, when it is not null, in the same spot and style (`text-[8.5px] font-mono font-bold …`). Use one tone → class map for every badge:

  | Tone | Class |
  |---|---|
  | `cinema` | `bg-rose-600/90` |
  | `upcoming` | `bg-amber-500/90` |
  | `requested` | `bg-slate-600/90` |
  | `searching` | `bg-sky-600/90` |
  | `downloading`, `rental` | `bg-[#635bff]/90` |
  | `error` | `bg-red-600/90` |
  | `kept` | `bg-emerald-600/90` |

  The favorite button stays.
- [ ] **Step 5:** Above the grid, when `enRouteMovies.length > 0`, render a section with a heading « En route » and the count. It is a horizontal scroll row (`flex gap-3 overflow-x-auto`) of small cards, `w-28` with a 2/3 poster and the title on one line. The `enRouteBadge(movie.releaseDate, libraryStates[movie.id])` badge sits on the poster, and a click opens the film like the grid does. Add a « Bibliothèque » heading above the grid only when the row is shown.
- [ ] **Step 6: Verify:** `npm test`, `npm run lint` and `npm run build` in `proto-ui` all pass with no new lint errors. Then start the dev server through `.claude/launch.json` (preview_start) and log in as a non-admin flatmate:
  - Films shows the En route row with its badges.
  - The grid has no Serveur, Physique, Streaming or Cinéma pills.
  - « Mes locations » narrows both the row and the grid.
  - Séries looks unchanged apart from the pills.
  - Capture a screenshot.
- [ ] **Step 7: Commit** `git commit -m "Sépare les films en route de la bibliothèque et ajoute « Mes locations »"`
