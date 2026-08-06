# Recommendation Optimizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a personalized movie chooser that uses shared SQLite memory, adaptive local scoring, at most two Gemini passes per session, and a two-session-per-day quota for non-admin users.

**Architecture:** Keep one SQLite database with every recommendation row scoped by `backstage_user_id`. The local engine owns eligibility, preference learning, diversity, questions, and fallback recommendations. An optional Gemini gateway receives only compact profiles and candidate IDs; it returns validated IDs, never creates movie data.

**Tech Stack:** Python 3.11, FastAPI, SQLite, Pydantic 2, `google-genai==1.75.0`, React/Vite/Tailwind, pytest.

## Global Constraints

- Administrators have unlimited recommendation sessions.
- Non-admin users have two started recommendation sessions per Europe/Paris calendar day.
- A recommendation session contains at most two Gemini calls and at most five questions.
- The local engine must produce a result when Gemini is disabled, unavailable, invalid, or over quota.
- TMDB is the only source of movie identity; Gemini may only select among supplied TMDB IDs.
- `shown`, `skipped`, `not_now`, `less_like_this`, `hard_reject`, and `already_seen` are distinct signals.
- Temporary negative signals expire; only `hard_reject` is a durable exclusion.
- Existing untracked files `_backstage-backstage-1_logs.txt` and `stripe-x-a24.md` must not be staged.

---

### Task 1: Add structured preference and AI usage persistence

**Files:**
- Modify: `backend/core/models.py` (`RecommendationEventType`)
- Modify: `backend/core/store.py` (`MediaStore.init_schema` and recommendation methods)
- Modify: `backend/config.py`
- Modify: `.env.example`
- Create: `tests/test_recommendation_store.py`

**Interfaces:**
- Produce `MediaStore.count_recommendation_sessions(user_id: str, day_start: datetime) -> int`.
- Produce `MediaStore.get_recommendation_usage(session_id: str) -> list[dict[str, Any]]`.
- Produce `MediaStore.record_recommendation_usage(payload: dict[str, Any]) -> dict[str, Any]`.
- Produce `MediaStore.upsert_media_recommendation_preference(user_id: str, media_id: str, fields: dict[str, Any])`.

- [ ] **Step 1: Write failing persistence tests**

```python
def test_recommendation_usage_and_daily_count_are_user_scoped(tmp_path):
    store = make_store(tmp_path)
    store.record_recommendation_usage_sync({
        "backstage_user_id": "hugo", "session_id": "s1", "model": "gemini-3.5-flash-lite",
        "input_tokens": 100, "output_tokens": 20, "cost_estimate_usd": 0.0001,
        "created_at": "2026-08-06T10:00:00+00:00",
    })
    assert store.count_recommendation_sessions_sync("hugo", "2026-08-06T00:00:00+00:00") == 0
    assert store.get_recommendation_usage_sync("s1")[0]["input_tokens"] == 100
```

- [ ] **Step 2: Run `py -m pytest -q tests/test_recommendation_store.py` and verify the missing-table/method failure.**
- [ ] **Step 3: Add additive SQLite tables `media_recommendation_preferences` and `ai_usage`, plus indexes by user/session/date. Extend `RecommendationEventType` with `skipped`, `not_now`, `hard_reject`, and `already_seen`.**
- [ ] **Step 4: Add `RECOMMENDATION_DAILY_LIMIT=2`, `RECOMMENDATION_TIMEZONE=Europe/Paris`, `GEMINI_API_KEY`, `GEMINI_MODEL=gemini-3.5-flash-lite`, and `GEMINI_MAX_OUTPUT_TOKENS=256` to configuration and `.env.example`.**
- [ ] **Step 5: Run the focused and full backend tests; commit `feat: persist recommendation preferences and ai usage`.**

### Task 2: Improve local profile scoring and adaptive questions

**Files:**
- Modify: `backend/core/recommendations.py`
- Modify: `backend/api.py` (`_recommendation_pool`, question/session helpers)
- Create: `tests/test_recommendation_scoring.py`

**Interfaces:**
- Produce `score_recommendation_candidate(candidate, profile, session_preferences, exclusions, now) -> RecommendationCandidate`.
- Produce `build_adaptive_question(candidates, profile, session_preferences) -> dict[str, Any] | None`.
- Produce `apply_recommendation_signal(profile, event_type, value, weight, now) -> TasteProfile`.

- [ ] **Step 1: Write failing tests for temporary refusal, hard rejection, decaying negative weight, session preference priority, and pair diversity.**

```python
def test_not_now_is_not_a_permanent_exclusion():
    preference = {"disposition": "not_now", "expires_at": "2026-09-01T00:00:00+00:00"}
    assert is_candidate_eligible(preference, datetime(2026, 8, 10, tzinfo=timezone.utc)) is True

def test_hard_reject_is_excluded():
    preference = {"disposition": "hard_reject", "expires_at": None}
    assert is_candidate_eligible(preference, datetime.now(timezone.utc)) is False
```

- [ ] **Step 2: Run focused tests and confirm they fail because the new signal and diversity interfaces do not exist.**
- [ ] **Step 3: Implement weighted signals: ratings/completions strongest, picks positive, `not_now` weak and expiring, `less_like_this` medium and decaying, `hard_reject` absolute. Keep `shown` neutral.**
- [ ] **Step 4: Add local candidate re-ranking with 15–20% exploration and a diversity penalty so a question pair does not repeat the same director, genre, or title.**
- [ ] **Step 5: Select the next question by the largest candidate split, falling back to mood questions and finally `Surprise`; cap the session at five questions.**
- [ ] **Step 6: Run focused and full backend tests; commit `feat: add adaptive recommendation scoring`.**

### Task 3: Enforce the per-user daily quota

**Files:**
- Modify: `backend/api.py` (`start_recommendation_session`)
- Modify: `backend/core/store.py`
- Create: `tests/test_recommendation_quota.py`

**Interfaces:**
- Produce `_recommendation_quota(current: AuthContext, store: MediaStore, now: datetime) -> dict[str, Any]`.
- Return `quota: {limit, used, remaining, unlimited}` in the session-start response.

- [ ] **Step 1: Write failing tests for two allowed user sessions, the third rejected with HTTP 429, unlimited admin access, Europe/Paris midnight reset, and user isolation.**

```python
def test_normal_user_is_rejected_after_two_daily_sessions(tmp_path):
    store = make_store(tmp_path)
    current = user_context("hugo")
    create_started_sessions(store, "hugo", count=2)
    with pytest.raises(HTTPException) as error:
        asyncio.run(start_recommendation_session(current, store))
    assert error.value.status_code == 429
```

- [ ] **Step 2: Run the quota tests and verify failure before implementation.**
- [ ] **Step 3: Check the role before counting; calculate the local calendar-day boundary in `Europe/Paris`, convert it to UTC, and count non-cancelled sessions.**
- [ ] **Step 4: Reserve a session only after the initial local candidate pool is available; cancel/refund the reservation when the startup operation fails.**
- [ ] **Step 5: Return remaining quota and a clear 429 detail to the UI. Run all backend tests; commit `feat: limit recommendation sessions per user`.**

### Task 4: Add the optional Gemini gateway and two-pass flow

**Files:**
- Modify: `requirements.txt` (add `google-genai==1.75.0`)
- Create: `backend/core/gemini_recommendations.py`
- Modify: `backend/api.py`
- Create: `tests/test_gemini_recommendations.py`

**Interfaces:**
- `GeminiRecommendationGateway.select_shortlist(profile: dict, candidates: list[dict]) -> GeminiShortlist`.
- `GeminiRecommendationGateway.select_final(profile: dict, answers: list[dict], candidates: list[dict]) -> GeminiSelection`.
- `GeminiSelection` fields: `tmdb_id: int`, `confidence: float`, `reason: str`.

- [ ] **Step 1: Write failing tests for disabled Gemini fallback, valid JSON selection, unknown-ID rejection, token usage persistence, and max output token configuration.**
- [ ] **Step 2: Run the focused tests and verify the gateway is absent/fails as expected.**
- [ ] **Step 3: Implement the gateway with `google.genai.Client`, compact JSON prompts, `response_mime_type="application/json"`, `max_output_tokens=256`, and no raw history.**
- [ ] **Step 4: Validate every returned ID against the candidate map; on any API, schema, timeout, or quota error, return the local result and record the failure without exposing secrets.**
- [ ] **Step 5: Wire call 1 after local candidate selection and call 2 only at final selection; store input/output tokens and estimated cost in `ai_usage`.**
- [ ] **Step 6: Run focused and full tests; commit `feat: add optional two-pass Gemini recommendations`.**

### Task 5: Add feedback controls and quota UX

**Files:**
- Modify: `proto-ui/src/api.js`
- Modify: `proto-ui/src/components/RecommendationFlow.jsx`
- Modify: `proto-ui/src/BackstagePrototype.jsx` only if the launcher needs quota props
- Create: `proto-ui/src/components/RecommendationFlow.test.jsx` only if a frontend test runner is introduced; otherwise verify through build and browser QA

**Interfaces:**
- `startRecommendationSession()` returns `{session, state, question, result, quota}`.
- Answer payloads use `answer: "picked" | "light" | "intense" | "surprise" | "skipped" | "not_now" | "less_like_this" | "already_seen"`.

- [ ] **Step 1: Add UI states for quota exhausted, local fallback, and Gemini unavailable.**
- [ ] **Step 2: Change the progress indicator from `1 / 10` to `1 / 5`.**
- [ ] **Step 3: Add compact actions `Pas maintenant`, `Pas mon style`, `Déjà vu`, and `Surprise`; do not interpret closing the modal as rejection.**
- [ ] **Step 4: Display remaining sessions for normal users and “Illimité” for admins.**
- [ ] **Step 5: Keep the compare-card interaction and ensure already shown IDs never reappear in the current session.**
- [ ] **Step 6: Run `npm run build` and `npm run lint`; manually verify normal-user quota, admin bypass, fallback, and feedback states; commit `feat: expose recommendation feedback and quota`.**

### Task 6: Verify observability, documentation, and deployment

**Files:**
- Modify: `docs/superpowers/specs/2026-08-06-recommendation-optimizer-design.md` only if implementation decisions change
- Modify: `README.md` or deployment documentation for Gemini variables and quota
- Modify: `BACKSTAGE_VISION_ARCHITECTURE_ROADMAP.md` to mark the recommendation algorithm, memory, quota, and Gemini fallback as implemented
- Create: `tests/test_recommendation_integration.py`

- [ ] **Step 1: Add integration tests covering full session start → five answers → final result, fallback without Gemini, daily quota, admin bypass, user isolation, and token usage rows.**
- [ ] **Step 2: Run `py -m pytest -q`, `npm run build`, `npm run lint`, and `git diff --check`.**
- [ ] **Step 3: Inspect `git status` and stage only intended tracked files.**
- [ ] **Step 4: Commit `test: verify personalized recommendation flow`.**
- [ ] **Step 5: Push `main` and `agent/backstage-docker-deployment`; rebuild and redeploy through Portainer, then verify `/health` and one normal-user plus one admin flow.**

## Self-review

- SQLite memory, nuanced refusal semantics, adaptive local scoring, two Gemini passes, local fallback, quota, admin bypass, UI feedback, token tracking, tests, and deployment verification each have an explicit task.
- No task creates one SQLite file per user; user isolation is consistently keyed by `backstage_user_id`.
- Gemini call counts are bounded by the session flow and the user quota is checked server-side.
- The plan preserves the existing `shown_tmdb_ids` anti-repeat behavior and upgrades it to a broader preference model.
