# Recommandations personnalisées Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a per-user, TMDB-backed movie chooser that learns from ratings, viewing behavior, lists, and up to ten modern interactive questions.

**Architecture:** Keep shared catalog metadata in `media`, move personal status/rating/favorite/review state into a user-media table, and record recommendation interactions as append-only events. A pure backend engine builds a taste profile, scores TMDB candidates, applies diversity, and returns a controlled-random result; a React flow asks adaptive visual questions and records the answers.

**Tech Stack:** FastAPI, SQLite, Pydantic, existing TMDB client, existing per-user Jellyfin playback synchronization, React 19, Vite, Tailwind CSS.

## Global Constraints

- Recommendations are independent per user.
- Jellyfin availability is not a candidate filter; playback history remains a preference signal.
- Films already seen by the current user are excluded.
- “À voir” and favorites provide a small bonus, not the dominant score.
- The interactive flow usually asks 5–7 questions and never more than 10.
- Durable taste is separated from one-session mood/preferences.
- The interface is centered, cinematic, restrained, and not kitsch.
- TMDB provides candidate metadata; no machine-learning service is introduced for the first version.

---

### Task 1: Add user-scoped media state and migrate existing personal fields

**Files:**
- Create: `backend/core/user_media_state.py`
- Modify: `backend/core/models.py`
- Modify: `backend/core/store.py`
- Modify: `backend/api.py:70-84,381-431,200-210`
- Create: `tests/test_user_media_state.py`

**Interfaces:**
- Consumes: authenticated user id, shared `Media`, and existing legacy media fields.
- Produces:

```python
class UserMediaState(BaseModel):
    backstage_user_id: str
    media_id: str
    status: Optional[str] = None
    rating: Optional[float] = Field(default=None, ge=0, le=5)
    review: Optional[str] = None
    is_favorite: bool = False
    added_to_watchlist_at: Optional[datetime] = None
    first_started_at: Optional[datetime] = None
    last_interacted_at: datetime

async def get_user_media_state(user_id: str, media_id: str) -> UserMediaState | None:
    pass

async def upsert_user_media_state(user_id: str, media_id: str, fields: dict[str, Any]) -> UserMediaState:
    pass

async def list_user_media_states(user_id: str) -> list[UserMediaState]:
    pass
```

- [ ] **Step 1: Write failing SQLite tests for isolated state.** Prove that two users can rate, favorite, and status the same media differently, and that a missing row returns `None`.
- [ ] **Step 2: Run `pytest tests/test_user_media_state.py -q` and confirm failure before schema/Store methods exist.**
- [ ] **Step 3: Add `user_media_state` with a composite primary key `(backstage_user_id, media_id)`, indexes by user/status, and additive initialization in `MediaStore.init_schema()`.** Store timestamps in ISO-8601 UTC.
- [ ] **Step 4: Add model conversion and async Store methods with an UPSERT that updates only provided personal fields.**
- [ ] **Step 5: Overlay personal fields in `GET /medias` and `GET /medias/{media_id}` for the authenticated user.** Keep catalog metadata (`title`, TMDB ids, synopsis, categories, cast, artwork) shared.
- [ ] **Step 6: Change `PATCH /medias/{media_id}` so `status`, `rating`, `review`, and favorite state require `get_current_user` and write to user state; catalog-only fields remain shared and admin-protected where applicable.** Preserve the existing `watched` and `watchlist` aliases.
- [ ] **Step 7: Migrate legacy single-user values exactly once to the first administrator’s user state when the new table is empty.** Do not overwrite an existing user state.
- [ ] **Step 8: Run `pytest tests/test_user_media_state.py tests/test_api.py -q` and confirm the tests pass.**
- [ ] **Step 9: Commit the user-scoped state.**

```bash
git add backend/core/user_media_state.py backend/core/models.py backend/core/store.py backend/api.py tests/test_user_media_state.py
git commit -m "feat(profile): isolate personal media state per user"
```

### Task 2: Record passive and explicit recommendation signals

**Files:**
- Create: `backend/core/recommendation_events.py`
- Modify: `backend/core/store.py`
- Modify: `backend/api.py`
- Create: `tests/test_recommendation_events.py`

**Interfaces:**
- Consumes: authenticated user id, media id when available, event type, numeric value, session id, and timestamp.
- Produces:

```python
RecommendationEventType = Literal[
    "shown", "picked", "dismissed", "more_like_this", "less_like_this",
    "question_answered", "session_completed",
]

class RecommendationEvent(BaseModel):
    id: str
    backstage_user_id: str
    session_id: Optional[str] = None
    media_id: Optional[str] = None
    event_type: RecommendationEventType
    value: Optional[str] = None
    numeric_value: Optional[float] = None
    created_at: datetime
```

- [ ] **Step 1: Write failing tests for append-only event insertion and per-user listing ordered newest-first.**
- [ ] **Step 2: Run `pytest tests/test_recommendation_events.py -q` and confirm failure.**
- [ ] **Step 3: Add `recommendation_events` with indexes on `(backstage_user_id, created_at)` and `(session_id, created_at)`.** Validate event types server-side.
- [ ] **Step 4: Add Store methods `record_recommendation_event` and `list_recommendation_events`.** Never accept a client-supplied user id; derive it from the session.
- [ ] **Step 5: Add `POST /recommendations/events` with payload fields `session_id`, `media_id`, `event_type`, `value`, and `numeric_value`.** Return the serialized event.
- [ ] **Step 6: Add tests for unauthorized requests, cross-user isolation, and invalid event types.**
- [ ] **Step 7: Run `pytest tests/test_recommendation_events.py -q` and commit.**

```bash
git add backend/core/recommendation_events.py backend/core/store.py backend/api.py tests/test_recommendation_events.py
git commit -m "feat(recommendations): record user feedback events"
```

### Task 3: Extend the TMDB client for candidate discovery

**Files:**
- Modify: `backend/core/tmdb.py`
- Modify: `backend/config.py`
- Create: `tests/test_tmdb_recommendations.py`

**Interfaces:**
- Consumes: genre ids, page, year/runtime filters, and the existing TMDB API key.
- Produces:

```python
async def discover_movies(
    self,
    *,
    with_genres: list[int] | None = None,
    page: int = 1,
    sort_by: str = "popularity.desc",
    min_vote_count: int = 50,
) -> list[dict[str, Any]]:
    pass
```

- [ ] **Step 1: Write a mocked HTTP test that asserts `/discover/movie` receives French language, genre ids, page, sort, and minimum vote count.**
- [ ] **Step 2: Run `pytest tests/test_tmdb_recommendations.py -q` and confirm failure.**
- [ ] **Step 3: Implement `discover_movies` using the existing retry client and return normalized candidates with `tmdb_id`, title, overview, genre ids, release date, runtime when available, vote average, popularity, and poster/backdrop paths.**
- [ ] **Step 4: Return an empty list for TMDB failures while logging the error, matching existing client behavior.**
- [ ] **Step 5: Run the TMDB tests and commit.**

```bash
git add backend/core/tmdb.py backend/config.py tests/test_tmdb_recommendations.py
git commit -m "feat(tmdb): discover movie candidates"
```

### Task 4: Implement the pure taste profile and scoring engine

**Files:**
- Create: `backend/core/recommendations.py`
- Create: `tests/test_recommendations.py`

**Interfaces:**
- Consumes: shared media metadata, user media states, per-user playback progress, recommendation events, and session preferences.
- Produces:

```python
class TasteProfile(BaseModel):
    genre_affinity: dict[str, float]
    keyword_affinity: dict[str, float]
    director_affinity: dict[str, float]
    actor_affinity: dict[str, float]
    preferred_runtime_minutes: tuple[int, int] | None
    confidence: float

class RecommendationCandidate(BaseModel):
    tmdb_id: int
    title: str
    score: float
    reasons: list[str]

def build_taste_profile(
    media: list[Media],
    user_states: list[UserMediaState],
    playback: list[PlaybackProgress],
    events: list[RecommendationEvent],
    now: datetime,
) -> TasteProfile:
    pass

def score_candidate(
    candidate: dict[str, Any],
    profile: TasteProfile,
    session_preferences: dict[str, Any],
    seen_tmdb_ids: set[int],
    watchlisted_tmdb_ids: set[int],
    now: datetime,
) -> RecommendationCandidate:
    pass

def choose_from_top(
    candidates: list[RecommendationCandidate],
    rng: Random,
    top_n: int = 8,
) -> RecommendationCandidate | None:
    pass
```

- [ ] **Step 1: Write failing tests for genre affinity from personal ratings, completion signals, abandonment penalties, recent-interaction decay, and different profiles for different users.**
- [ ] **Step 2: Write failing tests that prove watched media is excluded, watchlist/favorite is only a small bonus, TMDB quality is secondary, and Jellyfin availability is never consulted.**
- [ ] **Step 3: Implement normalized genre/keyword/director/actor feature aggregation.** Use personal ratings as the strongest positive signal, completed playback as a smaller positive signal, early abandonment and `less_like_this` as negative signals, and apply recency decay.
- [ ] **Step 4: Implement scoring with explicit constants in one mapping:** personal taste `0.65`, session preference `0.15`, TMDB quality `0.08`, watchlist/favorite bonus `0.05`, and novelty/diversity `0.07`. Keep the weights module-level so later tuning does not require changing call sites.
- [ ] **Step 5: Implement deterministic diversity reranking and seeded controlled randomness among the top eight candidates.** Return reasons such as `genre_match`, `watchlist_bonus`, `not_seen`, and `discovery_pick`.
- [ ] **Step 6: Add a low-confidence fallback that uses a small TMDB discovery pool and does not claim a detailed taste explanation.**
- [ ] **Step 7: Run `pytest tests/test_recommendations.py -q` and commit.**

```bash
git add backend/core/recommendations.py tests/test_recommendations.py
git commit -m "feat(recommendations): score personalized movie candidates"
```

### Task 5: Add server-enforced interactive recommendation sessions

**Files:**
- Create: `backend/core/recommendation_sessions.py`
- Modify: `backend/core/store.py`
- Modify: `backend/api.py`
- Create: `tests/test_recommendation_sessions.py`

**Interfaces:**
- Consumes: user id, taste profile, TMDB candidates, answer payload, and current question count.
- Produces:

```python
class RecommendationSession(BaseModel):
    id: str
    backstage_user_id: str
    question_count: int = 0
    session_preferences: dict[str, Any] = Field(default_factory=dict)
    status: Literal["active", "completed", "cancelled"] = "active"
    created_at: datetime
    completed_at: datetime | None = None

POST /recommendations/sessions
POST /recommendations/sessions/{session_id}/answers
POST /recommendations/sessions/{session_id}/finish
```

- [ ] **Step 1: Write failing tests for session ownership, question count increment, adaptive answer persistence, and the hard limit of 10 questions.**
- [ ] **Step 2: Run `pytest tests/test_recommendation_sessions.py -q` and confirm failure.**
- [ ] **Step 3: Add a SQLite `recommendation_sessions` table storing session preferences as JSON and status timestamps.**
- [ ] **Step 4: Implement `POST /recommendations/sessions` to build the user profile, create a session, and return the first question with a candidate card set.**
- [ ] **Step 5: Implement `POST /recommendations/sessions/{id}/answers` to validate ownership, accept one of the supported answers, record an event, update session preferences, increment the count, and either return another question or a final result.** Return `429`-style application data is not needed; return `409` with a clear message if the session is already complete and `422` if the count would exceed 10.
- [ ] **Step 6: Implement `POST /recommendations/sessions/{id}/finish` for explicit completion and final feedback.**
- [ ] **Step 7: Add tests for two users, TMDB failure fallback, early completion, ten-question completion, and stale session handling.**
- [ ] **Step 8: Run the session tests and commit.**

```bash
git add backend/core/recommendation_sessions.py backend/core/store.py backend/api.py tests/test_recommendation_sessions.py
git commit -m "feat(recommendations): add adaptive chooser sessions"
```

### Task 6: Build the modern recommendation flow

**Files:**
- Create: `proto-ui/src/components/RecommendationFlow.jsx`
- Modify: `proto-ui/src/api.js`
- Modify: `proto-ui/src/BackstagePrototype.jsx`
- Modify: `proto-ui/src/App.css`
- Test: `proto-ui` lint and build plus browser acceptance

**Interfaces:**
- Consumes: `POST /recommendations/sessions`, answer responses, and recommendation event API.
- Produces:

```jsx
<RecommendationFlow
    isDarkMode={isDarkMode}
    onClose={() => setShowRecommendationFlow(false)}
    onOpenMedia={(candidate) => openRecommendedMedia(candidate)}
/>
```

- [ ] **Step 1: Add API functions `startRecommendationSession`, `answerRecommendation`, `finishRecommendation`, and `recordRecommendationEvent` with server error messages preserved.**
- [ ] **Step 2: Add a centered `RecommendationFlow` surface with only the states `loading`, `question`, `result`, `empty`, and `error`.**
- [ ] **Step 3: Render TMDB poster cards for comparisons and concise choices: “Celui-ci”, “L’autre”, “Plus léger”, “Plus intense”, “Valeur sûre”, “Découverte”, and “Surprise”.**
- [ ] **Step 4: Render a restrained progress indicator such as `3 / 7`, without points, badges, confetti, rankings, or loud colors.**
- [ ] **Step 5: On the result state, render one primary candidate, up to two alternatives, the explanation reasons, and actions to open the centered film detail or relaunch the chooser.**
- [ ] **Step 6: Record shown, picked, dismissed, more-like-this, and less-like-this events without exposing another user’s state.**
- [ ] **Step 7: Add a “Surprise” path that skips a question but still respects the server’s ten-question maximum.**
- [ ] **Step 8: Make the flow full-screen on mobile and centered on desktop with smooth, short transitions.**
- [ ] **Step 9: Run `npm run lint` and `npm run build`.**
- [ ] **Step 10: Manually verify a new user with no ratings, a user with strong genre ratings, a user with watched films, TMDB failure, early result, ten-question cap, and relaunch.**
- [ ] **Step 11: Commit the recommendation UI.**

```bash
git add proto-ui/src/components/RecommendationFlow.jsx proto-ui/src/api.js proto-ui/src/BackstagePrototype.jsx proto-ui/src/App.css
git commit -m "feat(ui): add interactive movie chooser"
```

### Verification checklist

- Two users with different ratings and playback histories receive different candidate scores.
- Seen films are excluded for the current user.
- Jellyfin availability is never required for recommendations.
- Watchlist/favorite influence is visible but small.
- The flow normally ends within 5–7 questions and never exceeds 10.
- User answers improve the current session without overwriting durable taste accidentally.
- TMDB outages degrade to a clear local error or low-confidence fallback.
- `pytest -q` and `npm run lint && npm run build` pass.
