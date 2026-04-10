# AGENTS.md

OpenSentry Command Center -- Cloud dashboard for managing and viewing security cameras. FastAPI backend + React frontend with Clerk authentication.

## Build & Run

```bash
# Backend
cd backend
uv sync
uv run python start.py              # http://localhost:8000

# Frontend
cd frontend
npm install
npm run dev                          # http://localhost:5173
npm run build                        # Production build → backend/static/
```

## Configuration

Backend config is loaded from environment variables (see `backend/.env.example`).

**Required:**
- `CLERK_SECRET_KEY` / `CLERK_PUBLISHABLE_KEY` -- Clerk auth

**Optional:**
- `DATABASE_URL` -- defaults to `sqlite:///./opensentry.db`
- `FRONTEND_URL` -- CORS origin, defaults to `http://localhost:5173`
- `SEGMENT_CACHE_MAX_PER_CAMERA` -- segments cached in memory per camera (default 15)
- `SEGMENT_PUSH_MAX_BYTES` -- max bytes per pushed segment (default 2 MB)
- `CLEANUP_INTERVAL` -- run cache eviction every N playlist updates (default 20)
- `INACTIVE_CAMERA_CLEANUP_HOURS` -- free caches for cameras offline this long (default 24)
- `AUDIT_LOG_RETENTION_DAYS` -- stream log retention (default 7)

Frontend config: `VITE_CLERK_PUBLISHABLE_KEY`, `VITE_API_URL`, `VITE_LOCAL_HLS`.

## Project Structure

```
backend/
├── app/
│   ├── main.py                 # FastAPI app, CORS, SPA middleware, rate limiting, cleanup loop
│   ├── api/
│   │   ├── cameras.py          # Camera CRUD, groups, settings, alerts, media, audit logs
│   │   ├── nodes.py            # CloudNode registration, heartbeat, key rotation
│   │   ├── hls.py              # HLS playlist + in-memory segment cache + push-segment
│   │   ├── audit.py            # Stream access logs and statistics
│   │   └── webhooks.py         # Clerk subscription webhook handler
│   ├── core/
│   │   ├── auth.py             # Clerk JWT validation, V2 permission decoder, dependencies
│   │   ├── config.py           # Environment variable loading (Config class)
│   │   ├── clerk.py            # Clerk SDK init
│   │   └── database.py         # SQLAlchemy engine, session factory, Base
│   ├── models/
│   │   └── models.py           # All ORM models (see Data Models below)
│   └── schemas/
│       └── schemas.py          # Pydantic request/response schemas
├── start.py                    # Uvicorn entrypoint (0.0.0.0:8000, reload=True)
├── pyproject.toml              # Dependencies (FastAPI, SQLAlchemy, Clerk, etc.)
└── .env.example

frontend/
└── src/
    ├── pages/
    │   └── DashboardPage.jsx   # Camera grid with status cards and controls
    └── components/
        └── HlsPlayer.jsx      # HLS.js player with Clerk JWT auth
```

## Architecture

### Request flow

```
Browser ──JWT──→ FastAPI ──SQL──→ SQLite/PostgreSQL
                    ↕
CloudNode ──API Key──→ FastAPI ──RAM──→ in-memory segment cache
```

### Video streaming pipeline

1. CloudNode generates HLS segments via FFmpeg (2-second `.ts` files)
2. CloudNode calls `POST /api/cameras/{id}/push-segment?filename=segment_NNNNN.ts` with the raw `.ts` body and `X-Node-API-Key` header
3. Backend stores the bytes in `_segment_cache[camera_id][filename]` (max `SEGMENT_CACHE_MAX_PER_CAMERA` per camera, oldest evicted)
4. CloudNode calls `POST /api/cameras/{id}/playlist` with the rolling `stream.m3u8` text
5. Backend caches the rewritten playlist (segment filenames → relative `segment/<file>` proxy URLs)
6. Browser calls `GET /api/cameras/{id}/stream.m3u8` with JWT → served instantly from `_playlist_cache`
7. Browser fetches each segment via `GET /api/cameras/{id}/segment/{filename}` → served from `_segment_cache` in memory
8. Cache eviction sweeps every `CLEANUP_INTERVAL` playlist updates; inactive cameras are flushed by the daily cleanup loop

### SPA serving

`main.py` middleware routes:
- `/api/*` → FastAPI handlers
- `/assets/*` → static files from React build
- Everything else → `index.html` (SPA client-side routing)

## Authentication

### Clerk JWT (browser users)

`get_current_user()` dependency in `core/auth.py`:
1. Extracts `Authorization: Bearer <token>` header
2. Authenticates with Clerk SDK
3. Extracts `sub` (user_id), `org_id`, permissions from JWT claims
4. Returns `AuthUser` object

**V2 permission decoding** (`decode_v2_permissions()`):
- `o` claim contains org object with `fpm` (feature permission map) and `per` (permissions)
- `fea` claim contains feature list (e.g. `o:admin,o:cameras`)
- Decoded to `org:{feature}:{permission}` format

**Dependencies:**
- `require_view()` → needs `org:cameras:view_cameras` or admin
- `require_admin()` → needs `org:admin:admin` or `org:cameras:manage_cameras`

### API key (CloudNode)

CloudNode endpoints validate `X-Node-API-Key` or `Authorization: Bearer` header:
1. SHA-256 hash the provided key
2. Match against `api_key_hash` in `CameraNode` table
3. Extract `org_id` from the matched node

## Data Models

All models in `backend/app/models/models.py`. Every model has `org_id` for tenant isolation.

| Model | Key Fields | Purpose |
|-------|------------|---------|
| `Camera` | `camera_id`, `node_id`, `name`, `status`, `video_codec`, `audio_codec`, `group_id` | Camera device registered by CloudNode |
| `CameraNode` | `node_id`, `api_key_hash`, `hostname`, `status`, `upload_count` | Physical CloudNode device |
| `CameraGroup` | `name`, `color`, `icon` | User-defined camera grouping |
| `Media` | `camera_id`, `media_type`, `filename`, `data` (BLOB), `thumbnail` | Snapshots and recordings |
| `Alert` | `camera_id`, `detection_type`, `confidence`, `region_*` | Detection events (motion, face, object) |
| `Setting` | `key`, `value` | Per-org key-value settings |
| `AuditLog` | `event`, `user_id`, `ip_address`, `details` | Security audit trail |
| `StreamAccessLog` | `user_id`, `camera_id`, `ip_address`, `user_agent` | Stream playback audit |

## API Routes

### Router prefixes

| File | Prefix | Tags |
|------|--------|------|
| `cameras.py` | `/api` | api |
| `nodes.py` | `/api/nodes` | nodes |
| `hls.py` | `/api/cameras/{camera_id}` | streaming |
| `audit.py` | `/api` | audit |
| `webhooks.py` | `/api/webhooks` | webhooks |

### All endpoints

**cameras.py** (prefix `/api`):
- `GET /cameras` -- list cameras (view)
- `GET /cameras/{camera_id}` -- get camera (view)
- `POST /cameras/{camera_id}/codec` -- report codec (node API key)
- `GET /camera-groups` -- list groups (view)
- `POST /camera-groups` -- create group (admin)
- `DELETE /camera-groups/{group_id}` -- delete group (admin)
- `PUT /cameras/{camera_id}/group` -- assign group (admin)
- `GET /settings` -- all settings (view)
- `GET|POST /settings/notifications` -- notification settings
- `GET|POST /settings/recording` -- recording settings
- `GET /alerts` -- list alerts, filterable by `detection_type`, `camera_id`, `since_hours` (view)
- `GET /alerts/{alert_id}` -- get alert (view)
- `DELETE /alerts/{alert_id}` -- delete alert (admin)
- `GET /media` -- list media (view)
- `GET /media/{media_id}` -- get media (view)
- `DELETE /media/{media_id}` -- delete media (admin)
- `GET /audit-logs` -- audit logs (admin)
- `GET /health` -- health check (no auth)

**nodes.py** (prefix `/api/nodes`):
- `POST /register` -- CloudNode registration (API key)
- `POST /heartbeat` -- CloudNode heartbeat (API key)
- `GET /` -- list nodes (admin)
- `POST /` -- create node (admin)
- `GET /{node_id}` -- get node (admin)
- `DELETE /{node_id}` -- delete node (admin)
- `POST /{node_id}/rotate-key` -- rotate API key (admin)

**hls.py** (prefix `/api/cameras/{camera_id}`):
- `GET /stream.m3u8` -- HLS playlist served from cache (JWT)
- `GET /segment/{filename}` -- serve cached `.ts` segment from memory (JWT)
- `POST /push-segment?filename=…` -- CloudNode pushes `.ts` segment into cache (API key)
- `POST /playlist` -- update playlist (API key)
- `POST /codec` -- update codec info (API key)

**audit.py** (prefix `/api`):
- `GET /audit/stream-logs` -- stream access logs (admin)
- `GET /audit/stream-logs/stats` -- stream stats by camera/user/day (admin)

**webhooks.py** (prefix `/api/webhooks`):
- `POST /clerk` -- Clerk subscription events (webhook signature)

**Top-level** (`main.py`):
- `GET /api/health` -- `{"status": "healthy", "version": "2.0.0"}`

## CORS

Configured in `main.py`:
```python
cors_origins = [
    "http://localhost:5173",
    "http://localhost:8000",
    "https://opensentry-command.fly.dev",
]
```
Plus `FRONTEND_URL` if set. All methods, all headers, credentials allowed.

## Rate Limiting

Uses `slowapi`. No HLS-path endpoints are currently rate-limited; segment fetches are intentionally fast-path with no per-request DB work.

## Webhook Handling

`POST /api/webhooks/clerk` handles Clerk subscription events:
- Verifies signature with Svix (or accepts unsigned JSON if `CLERK_WEBHOOK_SECRET` not set)
- On `subscription.created`/`updated` with `pro_tier` plan → sets org member limit to unlimited
- On `subscription.deleted`/`cancelled` → resets to free tier limit (2 members)

## Key Patterns

**Tenant isolation:** Every query filters by `org_id` from the authenticated user/node.

**Error handling:** FastAPI `HTTPException` with appropriate status codes. Clerk auth failures return 401/403.

**Database sessions:** `get_db()` dependency yields a SQLAlchemy session per request.

**In-memory segment cache:** Live `.ts` segments live in `_segment_cache` (a `dict[camera_id, dict[filename, (bytes, ts)]]`) inside `hls.py`. Backend never touches S3 for live video. Recordings and snapshots are stored locally on the CloudNode.

**Codec detection:** CloudNode reports codec via `POST /api/cameras/{id}/codec` after the first segment is pushed. Stored on Camera model, injected into HLS playlist as `#EXT-X-CODECS`.

## Key Dependencies

- `fastapi` / `uvicorn` -- Web framework and ASGI server
- `sqlalchemy` -- ORM (SQLite dev, PostgreSQL production)
- `pydantic` -- Request/response validation
- `clerk-backend-api` -- Clerk authentication
- `pyjwt` -- JWT token handling
- `slowapi` -- Rate limiting
- `httpx` -- HTTP client
- `svix` -- Webhook signature verification
- `python-dotenv` -- Environment variable loading

## Development Notes

- Database tables auto-created on startup via `Base.metadata.create_all()`
- Backend serves React build as static files in production (SPA middleware in `main.py`)
- Frontend uses HLS.js for video playback with Clerk JWT for authenticated requests
- `VITE_LOCAL_HLS=true` bypasses backend and streams directly from CloudNode on localhost:8080
