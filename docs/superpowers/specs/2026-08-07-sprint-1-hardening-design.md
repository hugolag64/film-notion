# Sprint 1 Hardening - Design

## Objective

Make Backstage safe and reproducible for a family/LAN deployment: shared mutations are admin-only, playback progress is per user, playback checks rental access, authentication is rate limited, timezone data works in a clean environment, and secure deployment is documented.

## Decisions

1. Shared catalog routes that create, relink, refresh, or edit shared metadata require require_admin. Personal actions keep using /medias/{media_id}/personal and user_media_state.
2. Episode metadata stays shared, while watched state is stored per user in user_episode_state. API responses are calculated for the current user.
3. Jellyfin playback checks the current user, the media and rental state. Permanent administrative media is allowed; expired or unrelated temporary rentals return 403.
4. Login and password reset use an in-process sliding-window limiter with Retry-After. This is suitable for the current single-instance deployment.
5. tzdata is a pinned dependency. Cookie security and rate-limit settings are exposed in .env.example and docker-compose.yml.

## Out of scope

- React rewrite.
- External cache or queue.
- Full recommendation rating migration.
- Two-factor authentication.
- Multi-replica deployment.

## Acceptance criteria

- A regular user cannot mutate shared catalog metadata.
- Episode watched state is isolated between users.
- Expired rental cannot return a playback URL or resource.
- Login and reset are limited with 429 and Retry-After.
- Python suite passes in the documented environment.
- Secure deployment documentation covers HTTPS, VPN, secrets, backups and restoration.
- Frontend lint and build remain green.

End of design.
