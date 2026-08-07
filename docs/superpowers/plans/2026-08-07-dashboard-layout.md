# Dashboard Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify the Backstage header and compact the dashboard continuation section into a responsive horizontal row.

**Architecture:** Keep all behavior in the existing React shell and `DashboardHome` component. Change only layout classes, visible navigation labels, and the mode toggle presentation; existing callbacks remain the source of truth for actions.

**Tech Stack:** React 19, Vite, Tailwind CSS 4, oxlint.

## Global Constraints

- No backend, API, database, or dependency changes.
- Preserve existing callbacks for media, library, collection, search, admin, account, and theme actions.
- Keep native buttons, visible focus states, and responsive overflow behavior.

---

### Task 1: Lock the layout contract

**Files:**
- Create: `tests/test_dashboard_layout_contract.py`
- Test: `tests/test_dashboard_layout_contract.py`

- [ ] **Step 1: Write the failing source contract test**

```python
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_header_uses_compact_primary_navigation_and_right_aligned_utilities():
    source = (ROOT / "proto-ui/src/BackstagePrototype.jsx").read_text(encoding="utf-8")
    assert "['dashboard', 'Accueil']" in source
    assert "['library', 'Bibliothèque']" not in source
    assert "title=\"Changer de thème\"" in source
    assert "aria-label=\"Navigation principale\"" in source


def test_continue_watching_is_a_horizontal_compact_row():
    source = (ROOT / "proto-ui/src/components/DashboardHome.jsx").read_text(encoding="utf-8")
    assert "aria-label=\"Reprises en cours\"" in source
    assert "grid gap-4 md:grid-cols-2" not in source
    assert "flex gap-3 overflow-x-auto" in source
```

- [ ] **Step 2: Run the contract test and verify it fails**

Run: `python -m pytest tests/test_dashboard_layout_contract.py -q`

Expected: FAIL because the current header still contains `Bibliothèque` and the continuation section still uses a two-column grid.

### Task 2: Simplify the header

**Files:**
- Modify: `proto-ui/src/BackstagePrototype.jsx` in the top header JSX

- [ ] **Step 1: Implement the compact navigation**

Replace the two segmented navigation groups with one semantic navigation group containing `Accueil`, `Films`, and `Séries`. Keep the existing callbacks: `setActiveView('dashboard')` for Accueil and `setActiveView('library'); changeCollection(item)` for Films/Séries.

- [ ] **Step 2: Move utilities to the right and compact the theme button**

Keep search, add, admin, and account actions in the right utility group. Render the theme control as an icon-first button with `title="Changer de thème"` and an accessible label, while retaining the existing `setIsDarkMode` callback.

- [ ] **Step 3: Run the contract test**

Run: `python -m pytest tests/test_dashboard_layout_contract.py::test_header_uses_compact_primary_navigation_and_right_aligned_utilities -q`

Expected: PASS.

### Task 3: Compact continuation cards

**Files:**
- Modify: `proto-ui/src/components/DashboardHome.jsx` in `ContinueCard` and the `continueWatching` section

- [ ] **Step 1: Reduce the card footprint**

Change the continuation card from a large two-column panel to a compact poster-led card with a smaller image width, reduced padding, truncated metadata, and the same resume/detail buttons.

- [ ] **Step 2: Render a horizontal row**

Use a flex row with `flex gap-3 overflow-x-auto`, `aria-label="Reprises en cours"`, and a responsive fixed basis so six cards fit on desktop while mobile keeps cards readable. Slice the visible list to six items and let the row scroll when its card basis exceeds the viewport.

- [ ] **Step 3: Run the layout contract**

Run: `python -m pytest tests/test_dashboard_layout_contract.py::test_continue_watching_is_a_horizontal_compact_row -q`

Expected: PASS.

### Task 4: Verify and commit

**Files:**
- Modify: `proto-ui/src/BackstagePrototype.jsx`
- Modify: `proto-ui/src/components/DashboardHome.jsx`
- Create: `tests/test_dashboard_layout_contract.py`

- [ ] **Step 1: Run all backend tests**

Run: `$env:PYTHONPATH='.'; .venv\\Scripts\\pytest.exe -q`

Expected: all tests pass.

- [ ] **Step 2: Run frontend lint and build**

Run: `npm run lint` and `npm run build` from `proto-ui`.

Expected: both commands pass; the existing large-chunk warning may remain non-blocking.

- [ ] **Step 3: Review the diff and commit**

Run: `git diff --check` and `git diff --stat`, then commit with:

```bash
git add proto-ui/src/BackstagePrototype.jsx proto-ui/src/components/DashboardHome.jsx tests/test_dashboard_layout_contract.py
git commit -m "feat: simplify dashboard navigation and continuation layout"
```
