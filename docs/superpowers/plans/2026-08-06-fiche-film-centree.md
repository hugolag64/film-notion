# Fiche film centrée Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current side drawer with a centered, responsive film detail experience that preserves the library context.

**Architecture:** Keep media loading and mutation handlers in `BackstagePrototype.jsx` initially, but extract the detail rendering into a focused `FilmDetailView` component with explicit callbacks. The component will render the same user actions and playback/acquisition states in a centered desktop surface and full-screen mobile surface.

**Tech Stack:** React 19, Vite, Tailwind CSS, existing FastAPI media APIs, existing Jellyfin playback and TMDB data.

## Global Constraints

- The film detail view is centered and must not behave as a narrow side panel on desktop.
- Returning to the library preserves filters, sorting, and scroll position.
- The visual direction is modern, dark, cinematic, restrained, and free of kitsch gamification.
- The view must expose loading, error, and missing-data states.
- Series reuse the same detail foundation and keep episodes in a separate section.

---

### Task 1: Extract the film detail surface

**Files:**
- Create: `proto-ui/src/components/FilmDetailView.jsx`
- Modify: `proto-ui/src/BackstagePrototype.jsx:1291-1786`
- Test: `proto-ui` lint and build output

**Interfaces:**
- Consumes: the existing selected media object and callbacks already implemented in `BackstagePrototype.jsx`.
- Produces: a reusable component with this prop contract:

```jsx
<FilmDetailView
    media={selectedMovie}
    isDarkMode={isDarkMode}
    availability={mediaAvailability}
    rental={selectedRental}
    onClose={() => setSelectedMovie(null)}
    onPlay={openPlayer}
    onRequest={openAcquisition}
    onKeep={keepRental}
    onRate={handleRate}
    onStatusChange={handleStatusChange}
    onFavorite={toggleFavorite}
    onNotesChange={handleNotesChange}
    onSupportChange={handleSupportChange}
    onCinemaToggle={toggleCinema}
    onCinemaDateChange={handleDateChange}
    onRelink={openRelinkForMovie}
    onAddGenre={handleAddGenre}
    onRemoveGenre={handleRemoveGenre}
    onAddCast={handleAddCastActor}
    onRemoveCast={handleRemoveCastActor}
/>
```

- [ ] **Step 1: Create the component shell and move the existing selected-film JSX into it.** Keep every existing action label and callback behavior unchanged while removing direct references to parent state that are not passed as props.
- [ ] **Step 2: Add explicit fallback rendering for missing `poster`, `backdrop`, `synopsis`, `director`, `cast`, and `genre` values.** Empty values must render a compact fallback or disappear without leaving a blank section.
- [ ] **Step 3: Replace the parent drawer block with the component invocation using the full prop contract from this task and keep the series detail rendering untouched.** The parent remains the owner of selection and asynchronous state.
- [ ] **Step 4: Run `npm run lint` from `proto-ui` and fix every lint error introduced by the extraction.**
- [ ] **Step 5: Run `npm run build` from `proto-ui` and confirm the production bundle succeeds.**
- [ ] **Step 6: Commit the extraction.**

```bash
git add proto-ui/src/components/FilmDetailView.jsx proto-ui/src/BackstagePrototype.jsx
git commit -m "refactor(ui): extract film detail view"
```

### Task 2: Make the detail surface centered and responsive

**Files:**
- Modify: `proto-ui/src/components/FilmDetailView.jsx`
- Modify: `proto-ui/src/App.css`
- Test: `proto-ui` build plus browser acceptance checklist

**Interfaces:**
- Consumes: the `FilmDetailView` prop contract from Task 1.
- Produces: a centered detail surface with stable close behavior and mobile full-screen layout.

- [ ] **Step 1: Replace the drawer positioning classes with a centered overlay.** Use a fixed backdrop, a centered max-width surface, and an internal scroll region; do not use a left or right anchored panel.
- [ ] **Step 2: Add a desktop layout with a visual hero row.** Place poster/backdrop context and title/actions above the information grid, then render synopsis, metadata, rating, notes, and actions below it.
- [ ] **Step 3: Add the mobile breakpoint.** At narrow widths the surface must occupy the viewport, keep the close control visible, and stack poster, metadata, synopsis, and actions without horizontal overflow.
- [ ] **Step 4: Add keyboard and backdrop behavior.** `Escape` closes the view, clicking the backdrop closes it, clicking inside does not, and focus remains usable for form controls.
- [ ] **Step 5: Preserve library context.** Before opening the detail view, store the current scroll position in a ref; on close, restore it after the selected media state is cleared. Do not reset `filters`, `sort`, `activeFilter`, or `searchQuery`.
- [ ] **Step 6: Verify manually with a film containing full TMDB metadata, a film with missing metadata, desktop width, and mobile width.** Confirm that Lire, Favori, À voir, rating, notes, acquisition, and close still work.
- [ ] **Step 7: Run `npm run lint` and `npm run build`.**
- [ ] **Step 8: Commit the centered responsive surface.**

```bash
git add proto-ui/src/components/FilmDetailView.jsx proto-ui/src/App.css proto-ui/src/BackstagePrototype.jsx
git commit -m "feat(ui): center film detail experience"
```

### Task 3: Align the series detail entry point

**Files:**
- Create: `proto-ui/src/components/MediaDetailShell.jsx`
- Modify: `proto-ui/src/BackstagePrototype.jsx`
- Test: `proto-ui` lint and build

**Interfaces:**
- Consumes: the centered surface behavior from Task 2 and the existing series detail state (`seriesTab`, `seriesEpisodes`, `seriesProgress`).
- Produces: one shared centered shell that FilmDetailView and the existing series detail view use for backdrop, close, scroll, and mobile behavior.

- [ ] **Step 1: Extract only shared overlay behavior into `MediaDetailShell`.** The shell owns no movie or series business logic; it accepts `children`, `onClose`, `isDarkMode`, and `ariaLabel`.
- [ ] **Step 2: Wrap `FilmDetailView` and the existing series detail markup with the shell.** Keep series tabs and episode interactions unchanged.
- [ ] **Step 3: Verify that closing either film or series restores the same library context.**
- [ ] **Step 4: Run `npm run lint` and `npm run build`.**
- [ ] **Step 5: Commit the shared shell.**

```bash
git add proto-ui/src/components/MediaDetailShell.jsx proto-ui/src/components/FilmDetailView.jsx proto-ui/src/BackstagePrototype.jsx
git commit -m "refactor(ui): share centered media detail shell"
```

### Verification checklist

- `npm run lint` passes in `proto-ui`.
- `npm run build` passes in `proto-ui`.
- The film view is centered on desktop and full-screen on mobile.
- The side drawer no longer exists for film details.
- The close path preserves filters, sorting, search, and scroll position.
- Existing playback, acquisition, rental, rating, favorite, notes, TMDB relink, and metadata actions still work.
