# Backstage Docker Deployment Implementation Plan

> For agentic workers: use a plan-execution workflow task by task. Steps use checkbox syntax.

**Goal:** Run the existing Backstage backend and React frontend as a rebuildable Docker Compose service with persistent SQLite data outside the container on the server SSD.

**Architecture:** Build React in a Node stage, copy proto-ui/dist into a Python runtime image, and launch main.py. Compose mounts a host data directory at /data, sets DB_PATH=/data/backstage.db, exposes /health, and leaves Jellyfin/Radarr/Sonarr as external services.

**Tech Stack:** Python 3.11, NiceGUI/FastAPI, SQLite, React 19, Vite, Node 22 Alpine, Docker Compose.

## Global constraints

- First deployment uses the SSD; the persistent data path must move to the future disk without code changes.
- The container must not be the only location of user data.
- .env stays outside Git and API keys stay server-side.
- Jellyfin, Radarr, Sonarr, Seerr, Portainer, and the download client stay outside this Compose stack.
- Healthcheck depends only on Backstage.
- Automatic media deletion is disabled.
- Existing user modifications are untouched; commit only task files.

---

### Task 1: Add an isolated health endpoint

Files:
- Modify backend/api.py
- Modify main.py
- Test tests/test_api.py

Interfaces:
- health_router exposes GET /health and returns {"status": "ok"}.
- main.py includes health_router separately from the /api router.

- [ ] Step 1: Add a failing route registration test.

~~~python
from backend.api import health_router

def test_health_route_is_registered_without_media_dependencies():
    routes = {route.path for route in health_router.routes}
    assert "/health" in routes
~~~

Run: .venv\Scripts\python.exe -m pytest tests/test_api.py::test_health_route_is_registered_without_media_dependencies -q
Expected: FAIL because health_router is undefined.

- [ ] Step 2: Implement health_router in backend/api.py.

~~~python
health_router = APIRouter(tags=["health"])

@health_router.get("/health")
async def health_check():
    return {"status": "ok"}
~~~

Import and include health_router in main.py before or after the existing API router.

- [ ] Step 3: Run .venv\Scripts\python.exe -m pytest tests/test_api.py -q.
Expected: PASS.

- [ ] Step 4: Commit only tests/test_api.py, backend/api.py, and main.py.

~~~powershell
git add tests/test_api.py backend/api.py main.py
git commit -m "feat: add standalone health endpoint"
~~~

### Task 2: Add the multi-stage image and Compose service

Files:
- Create Dockerfile
- Create .dockerignore
- Create docker-compose.yml
- Modify .env.example

Interfaces:
- docker build -t backstage:local . creates an image containing /app/proto-ui/dist/index.html.
- Service backstage listens on container port 8090 and mounts BACKSTAGE_DATA_DIR, defaulting to ./data/backstage, at /data.
- Container environment sets DB_PATH=/data/backstage.db and PORT=8090.

- [ ] Step 1: Create .dockerignore containing .git, .env, .venv, Python caches, SQLite runtime files, tests, docs, legacy, proto-ui/node_modules, and proto-ui/dist.

- [ ] Step 2: Create Dockerfile with a node:22-alpine frontend-build stage, npm ci, npm run build, and a python:3.11-slim runtime stage. The runtime copies requirements.txt, installs it without pip cache, copies main.py, Logo.png, backend, and the generated dist directory, creates /data, exposes 8090, and runs python main.py.

- [ ] Step 3: Create docker-compose.yml with one backstage service:
  - build context is the repository root;
  - image is backstage:local;
  - env_file is .env;
  - environment sets DB_PATH=/data/backstage.db and PORT=8090;
  - ports maps BACKSTAGE_PORT, default 8090, to 8090;
  - volumes maps BACKSTAGE_DATA_DIR, default ./data/backstage, to /data;
  - restart is unless-stopped;
  - healthcheck runs Python urllib against http://127.0.0.1:8090/health every 30 seconds with a 5 second timeout, 3 retries, and a 20 second start period.

- [ ] Step 4: Append BACKSTAGE_PORT=8090 and BACKSTAGE_DATA_DIR=./data/backstage to .env.example without changing existing media-server variables.

- [ ] Step 5: Run docker compose config.
Expected: one backstage service, port 8090, volume target /data, and healthcheck /health.

- [ ] Step 6: Run docker build -t backstage:local .
Expected: successful build with the compiled frontend in the final image.

- [ ] Step 7: Commit only Dockerfile, .dockerignore, docker-compose.yml, and .env.example.

~~~powershell
git add Dockerfile .dockerignore docker-compose.yml .env.example
git commit -m "feat: add Docker Compose deployment"
~~~

### Task 3: Document deployment and future storage migration

Files:
- Create docs/deployment.md

Interfaces:
- Procedure starts from /srv/apps/backstage.
- Data contract is host path -> /data -> /data/backstage.db.

- [ ] Step 1: Document these exact operations:
  - create /srv/apps/backstage and /srv/data/backstage;
  - clone the repository;
  - copy .env.example to .env;
  - set the server values;
  - run docker compose up -d --build;
  - inspect docker compose ps and logs;
  - verify curl http://127.0.0.1:8090/health;
  - update with git pull followed by docker compose up -d --build;
  - migrate by stopping Compose, copying /srv/data/backstage to the future disk, verifying backstage.db, changing BACKSTAGE_DATA_DIR, and restarting;
  - state that the SSD is not a backup and automatic media deletion is disabled.

- [ ] Step 2: Review the document for destructive commands. Migration must verify the copy before removing or abandoning the old path.

- [ ] Step 3: Commit only docs/deployment.md.

~~~powershell
git add docs/deployment.md
git commit -m "docs: document Backstage deployment"
~~~

### Task 4: Verify persistence and hand off server commands

Files:
- No changes unless verification finds a defect in Tasks 1 to 3.

- [ ] Step 1: Create the explicitly disposable directory data/backstage-verification.

- [ ] Step 2: Set BACKSTAGE_DATA_DIR to ./data/backstage-verification, run docker compose up -d --build, and inspect docker compose ps. Expected status: healthy.

- [ ] Step 3: Request /health and verify data/backstage-verification/backstage.db exists.

- [ ] Step 4: Run docker compose up -d --force-recreate and verify the same host database file still exists.

- [ ] Step 5: Run .venv\Scripts\python.exe -m pytest -q, then npm run lint and npm run build from proto-ui. Expected: all existing tests pass, lint passes, and Vite produces dist.

- [ ] Step 6: Run docker compose down and remove only the explicitly named disposable data/backstage-verification directory. Do not remove .env, backstage.db, or the real server data directory.

