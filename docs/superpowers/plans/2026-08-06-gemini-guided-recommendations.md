# Gemini-Guided Recommendation Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Gemini choose a short personalized question path once per session, collect up to five answers locally, then make one final film selection from Backstage's eligible TMDB candidates.

**Architecture:** Backstage remains authoritative for user memory, candidate eligibility, question rendering, quotas, and final candidate validation. A new Gemini planner returns only validated question axes; local question builders render film comparisons or choice buttons without additional Gemini calls. A final Gemini call receives the persisted profile, selected axes, answers, and eligible candidates and may select only one supplied TMDB ID.

**Tech Stack:** FastAPI/Python, Pydantic, SQLite through `MediaStore`, Gemini Developer API, React/Vite/Tailwind.

## Global Constraints

- A standard user may start at most 2 recommendation sessions per day; admin users remain unlimited.
- A session may contain at most 5 questions.
- Gemini is optional; disabled, invalid, or failed Gemini calls fall back to deterministic local behavior.
- Gemini may make at most 2 calls per session: one planner call and one final selection call.
- Films shown recently, already watched, rated, or explicitly rejected remain excluded by the local engine.
- Gemini IDs are accepted only when they belong to the local candidate list.
- User recommendation events and answers remain isolated by `backstage_user_id` in SQLite.

---

### Task 1: Define the planner contract and local question builders

**Files:**
- Modify: `backend/core/gemini_recommendations.py`
- Modify: `backend/core/recommendations.py`
- Test: `tests/test_gemini_recommendations.py`
- Test: `tests/test_recommendations.py`

**Interfaces:**
- `GeminiQuestionPlan(axes: list[str], usage: dict[str, int])` accepts only `movie_compare`, `mood`, `genre`, and `era` axes after validation.
- `GeminiRecommendationGateway.plan_questions(profile: dict, recent_axes: list[str]) -> GeminiQuestionPlan | None` performs one JSON planner request and limits the result to five unique supported axes.
- `build_local_question(axis: str, candidates: list[RecommendationCandidate], profile: TasteProfile, session_preferences: dict[str, Any]) -> dict[str, Any] | None` returns a serializable local question.

- [ ] **Step 1: Write failing tests** for planner parsing/validation and local question shapes: a valid plan keeps supported unique axes, unknown axes are ignored, a `movie_compare` question has two candidate options, and `mood`/`genre`/`era` questions have local choice options.
- [ ] **Step 2: Run the focused tests and verify they fail** because the planner method and local question builder do not exist.
- [ ] **Step 3: Implement the smallest planner model and gateway method** using structured JSON with `axes`, and keep the prompt limited to profile/recent axes/allowed axes rather than sending the full movie catalogue.
- [ ] **Step 4: Implement deterministic local builders** that select eligible candidates and create choice questions without network calls.
- [ ] **Step 5: Run focused tests and verify they pass.**
- [ ] **Step 6: Commit** with `feat: add gemini question planning contract`.

### Task 2: Integrate the two-call flow and persistent question memory

**Files:**
- Modify: `backend/api.py`
- Modify: `backend/core/models.py`
- Modify: `docs/recommendation-optimizer.md`
- Test: `tests/test_recommendation_integration.py`
- Test: `tests/test_recommendation_memory_regression.py`

**Interfaces:**
- `_recommendation_profile(current, store) -> tuple[TasteProfile, list[RecommendationEvent]]` supplies the planner with the current user's local profile and event history.
- `_recommendation_question(session, axis, candidates, profile) -> dict[str, Any] | None` creates the next local question and marks its axis in session preferences.
- Session preferences persist `question_plan`, `current_question_axis`, `answers`, and `shown_tmdb_ids`.

- [ ] **Step 1: Write failing integration tests** asserting one planner usage plus one final usage, five local answers produce one final Gemini call, planner axes are stored in the session, and a new session avoids recent axes and recent shown films.
- [ ] **Step 2: Run the focused integration tests and verify they fail** against the current shortlist flow.
- [ ] **Step 3: Replace the start-session shortlist call** with the planner call, persist a validated fallback plan when Gemini is disabled/invalid, and keep the local candidate pool authoritative.
- [ ] **Step 4: Change answer handling** to append the answer to session preferences, record the axis marker in SQLite, choose the next axis locally, and finish when the plan ends or five questions are answered.
- [ ] **Step 5: Send all persisted answers and the eligible local pool to the final Gemini call** and retain local fallback selection on failure.
- [ ] **Step 6: Correct the recorded cost estimate** to the configured Gemini 3.5 Flash-Lite standard rates: `$0.30 / 1M` input tokens and `$2.50 / 1M` output tokens.
- [ ] **Step 7: Run focused tests and verify they pass.**
- [ ] **Step 8: Commit** with `feat: route recommendations through local question plans`.

### Task 3: Render planner-selected question types in the React flow

**Files:**
- Modify: `proto-ui/src/components/RecommendationFlow.jsx`
- Test: `proto-ui` lint/build checks

**Interfaces:**
- Existing recommendation endpoints remain unchanged at the transport level.
- Questions with `type: "compare"` continue to render posters; questions with `type: "choice"` render compact modern choice buttons and send their declared answer/value.

- [ ] **Step 1: Add the choice-question rendering path** and make the progress indicator use the server-provided question count/maximum.
- [ ] **Step 2: Ensure local choice answers use the same answer endpoint and preserve the existing loading/error/quota states.**
- [ ] **Step 3: Run `npm run lint` and `npm run build` and verify both pass.**
- [ ] **Step 4: Commit** with `feat: render adaptive recommendation questions`.

### Task 4: Full verification and handoff

**Files:**
- Verify: `backend`, `tests`, `proto-ui`

- [ ] **Step 1: Run `py -m pytest -q`.**
- [ ] **Step 2: Run `npm run lint` and `npm run build` in `proto-ui`.**
- [ ] **Step 3: Run `git diff --check` and inspect `git status --short`.**
- [ ] **Step 4: Confirm the two user-owned untracked files remain untouched and report the final commits, limits, and measured token usage fields.**
