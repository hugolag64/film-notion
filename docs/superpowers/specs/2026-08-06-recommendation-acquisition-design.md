# Recommendation confirmation and acquisition

## Goal

When a user validates the final recommendation, Backstage adds the film to the shared library and requests its download with the administrator's default acquisition profile.

## Behaviour

- The final recommendation remains the only film a session may confirm.
- Confirmation is idempotent by TMDB ID: an existing library item is reused and an active acquisition is not submitted twice.
- The created or reused media has no personal rating and keeps the `À regarder` status unless the user already has a different personal state.
- Seerr is preferred when configured; Radarr is the direct fallback.
- The exact Radarr quality profile name is `1080 FR - max 10go`.
- The root folder comes from the configured administrator default; if no explicit default exists, the first Radarr root folder is used.
- If the library addition succeeds but acquisition is unavailable or misconfigured, the film remains in the library and the response contains a retryable download error.
- Each Gemini planner call receives recent plan markers and the session identifier; the server records the chosen plan immediately and rejects a repeated recent plan in favour of a local rotation.

## API shape

`POST /api/recommendations/sessions/{session_id}/confirm`

```json
{ "tmdb_id": 123, "download": true }
```

The response contains the shared `media`, the current `availability` when present, and a user-readable `download_error` when the acquisition request could not be submitted.

## Safety

- The session owner is checked.
- The TMDB ID must match the session's completed recommendation event.
- Admin-only acquisition defaults are resolved server-side; clients cannot select an arbitrary profile or root folder through this endpoint.
- Remote provider failures do not delete the local library item.

## Cost and personalization

The system keeps two Gemini calls per session. The first plan is never reused as a cache; recent plan markers are supplied so every new session can choose a different path. Token cost is reduced by compact prompts and by avoiding a planner call when the local candidate pool is empty.
