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
- `LOG_RETENTION_DAYS` -- stream + MCP + audit log retention (default 90)

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
│   │   ├── incidents.py        # AI-generated incident reports (CRUD + evidence blobs)
│   │   ├── mcp_keys.py         # MCP API key generation / listing / revocation
│   │   ├── mcp_activity.py     # MCP tool call activity logs, stats, SSE stream
│   │   ├── install.py          # Signed CloudNode installer endpoints
│   │   ├── ws.py               # WebSocket helpers
│   │   └── webhooks.py         # Clerk subscription webhook handler
│   ├── mcp/
│   │   └── server.py           # FastMCP server + 22 tools (cameras, nodes, incidents w/ clips)
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
├── pyproject.toml              # Dependencies (FastAPI, SQLAlchemy, Clerk, FastMCP, etc.)
└── .env.example

frontend/
└── src/
    ├── pages/
    │   ├── DashboardPage.jsx       # Camera grid with status cards and controls
    │   ├── McpPage.jsx             # MCP key management + agent activity + incident list
    │   ├── AdminPage.jsx           # Stream logs, MCP activity, audit trail
    │   └── DocsPage.jsx            # In-app documentation
    └── components/
        ├── HlsPlayer.jsx           # HLS.js player with Clerk JWT auth
        └── IncidentReportModal.jsx # Incident detail view (markdown + evidence)
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
| `Setting` | `key`, `value` | Per-org key-value settings |
| `AuditLog` | `event`, `user_id`, `ip_address`, `details` | Security audit trail |
| `StreamAccessLog` | `user_id`, `camera_id`, `ip_address`, `user_agent` | Stream playback audit |
| `Incident` | `title`, `summary`, `report`, `severity`, `status`, `camera_id`, `created_by`, `resolved_at`, `resolved_by` | AI-generated incident report (open/ack/resolved/dismissed) |
| `IncidentEvidence` | `incident_id`, `kind` (`snapshot`\|`clip`\|`observation`), `text`, `camera_id`, `data` (BLOB), `data_mime` | Snapshot image, video clip (MPEG-TS bytes), or text observation attached to an incident |
| `McpApiKey` | `name`, `key_hash`, `last_used_at`, `revoked_at` | MCP API keys (org-scoped, SHA-256 hashed) |
| `McpToolCall` | `key_id`, `tool_name`, `params_json`, `status`, `duration_ms`, `error` | MCP tool call audit log |

Validation constants (also in `models.py`):
- `INCIDENT_STATUSES` = `{"open", "acknowledged", "resolved", "dismissed"}`
- `INCIDENT_SEVERITIES` = `{"low", "medium", "high", "critical"}`

## API Routes

### Router prefixes

| File | Prefix | Tags |
|------|--------|------|
| `cameras.py` | `/api` | api |
| `nodes.py` | `/api/nodes` | nodes |
| `hls.py` | `/api/cameras/{camera_id}` | streaming |
| `audit.py` | `/api` | audit |
| `incidents.py` | `/api/incidents` | incidents |
| `mcp_keys.py` | `/api/mcp` | mcp |
| `mcp_activity.py` | `/api/mcp/activity` | mcp-activity |
| `install.py` | (none) | installation |
| `ws.py` | (none) | ws |
| `webhooks.py` | `/api/webhooks` | webhooks |

### All endpoints

**cameras.py** (prefix `/api`):
- `GET /cameras` -- list cameras (view)
- `GET /cameras/{camera_id}` -- get camera (view)
- `POST /cameras/{camera_id}/snapshot` -- ask the node to capture & store a snapshot locally (view)
- `POST /cameras/{camera_id}/recording` -- start/stop recording on the node (view)
- `POST /cameras/{camera_id}/codec` -- report codec, called by CloudNode after first segment (node API key)
- `GET /camera-groups` -- list groups (view)
- `POST /camera-groups` -- create group (admin)
- `DELETE /camera-groups/{group_id}` -- delete group (admin)
- `PUT /cameras/{camera_id}/group` -- assign group (admin)
- `GET /settings` -- all settings (view)
- `GET /settings/recording` -- recording settings (view)
- `POST /settings/recording` -- update recording settings (admin)
- `GET /audit-logs` -- audit logs (admin)
- `POST /settings/danger/wipe-logs` -- permanently delete all stream + MCP logs (admin, requires `admin` feature flag)
- `POST /settings/danger/full-reset` -- wipe all nodes/cameras/logs/settings for the org (admin, requires `admin` feature flag)

**nodes.py** (prefix `/api/nodes`):
- `POST /validate` -- validate node_id + API key pair, used by CloudNode setup wizard (API key)
- `POST /register` -- CloudNode registration (API key)
- `POST /heartbeat` -- CloudNode heartbeat (API key)
- `GET /` -- list nodes (admin)
- `GET /plan` -- current plan, usage, and limits for the org (any signed-in user)
- `POST /` -- create node (admin, requires active billing)
- `GET /ws-status` -- which org nodes are currently WebSocket-connected (admin)
- `GET /{node_id}` -- get node (admin)
- `DELETE /{node_id}` -- delete node (admin)
- `POST /{node_id}/rotate-key` -- rotate API key (admin)

**hls.py** (prefix `/api/cameras/{camera_id}`):
- `GET /stream.m3u8` -- HLS playlist served from cache (JWT)
- `GET /segment/{filename}` -- serve cached `.ts` segment from memory (JWT)
- `POST /push-segment?filename=…` -- CloudNode pushes `.ts` segment into cache (API key)
- `POST /playlist` -- update playlist (API key)

**audit.py** (prefix `/api`):
- `GET /audit/stream-logs` -- stream access logs (admin)
- `GET /audit/stream-logs/stats` -- stream stats by camera/user/day (admin)

**incidents.py** (prefix `/api/incidents`):
- `GET /` -- list incidents with optional `status`, `severity`, `camera_id`, `limit`, `offset` (admin)
- `GET /counts` -- aggregate counts (open, open_critical, open_high, total) (admin)
- `GET /{incident_id}` -- incident detail with full evidence list (admin)
- `PATCH /{incident_id}` -- update status, severity, summary, or report (admin)
- `DELETE /{incident_id}` -- delete incident + cascade evidence (admin)
- `GET /{incident_id}/evidence/{evidence_id}` -- stream snapshot or clip blob by content type (admin)
- `GET /{incident_id}/evidence/{evidence_id}/playlist.m3u8` -- synthetic single-segment HLS playlist for clip playback (admin)

**mcp_keys.py** (prefix `/api/mcp`):
- `POST /keys` -- generate a new MCP API key, returns the plaintext `osc_...` once (admin, requires active billing)
- `GET /keys` -- list MCP API keys for the org (admin)
- `DELETE /keys/{key_id}` -- revoke an MCP API key (admin)

**mcp_activity.py** (prefix `/api/mcp/activity`):
- `GET /stream` -- SSE stream of live MCP tool calls (admin)
- `GET /recent` -- recent tool calls (admin)
- `GET /sessions` -- session summaries (admin)
- `GET /stats` -- aggregated stats by tool / key / time (admin)
- `GET /logs` -- MCP tool call log, filterable (admin)
- `GET /logs/stats` -- summary counts for logs (admin)

**install.py** (no prefix):
- `GET /install.sh` / `GET /install.ps1` -- signed CloudNode installer scripts (no auth)
- `GET /mcp-setup.sh` / `GET /mcp-setup.ps1` -- signed MCP setup helpers (no auth)

**ws.py** (no prefix):
- `WS /ws/node` -- WebSocket channel for CloudNode realtime control (API key in query)

**webhooks.py** (prefix `/api/webhooks`):
- `POST /clerk` -- Clerk subscription events (webhook signature)

**mcp/server.py** — FastMCP streamable HTTP server mounted at `/mcp` via FastMCP.
Authenticates with `Authorization: Bearer osc_...` against `McpApiKey.key_hash`.
Exposes 22 tools:

| Tool | Kind | Purpose |
|------|------|---------|
| `list_cameras` | read | All cameras with status/codec/group |
| `get_camera` | read | One camera by id |
| `get_stream_url` | read | Authenticated HLS URL for a camera |
| `view_camera` | visual | Live JPEG from a camera (agent can see it) |
| `watch_camera` | visual | Multi-frame burst (2-10 frames, 1-30s apart) |
| `list_camera_groups` | read | Camera groups for the org |
| `list_nodes` | read | CloudNodes + their status |
| `get_node` | read | One node by id |
| `get_recording_settings` | read | Current recording config |
| `get_stream_logs` | read | Stream access audit entries |
| `get_stream_stats` | read | Aggregated views by camera/user/day |
| `get_system_status` | read | Org-wide snapshot (cameras on/offline, plan, nodes) |
| `create_incident` | write | Open a new incident (title, summary, severity) |
| `attach_snapshot` | write | Capture a JPEG and attach it as evidence |
| `attach_clip` | write | Save the recent live buffer as a video clip on an incident (pulls from in-memory HLS cache) |
| `add_observation` | write | Append a text observation to an incident |
| `update_incident` | write | Change status / severity / summary / report body (revisions) |
| `finalize_incident` | write | Write the markdown report body for the first time |
| `list_incidents` | read | Previous incidents (filter by status/severity/camera) |
| `get_incident` | read | Full detail of one incident incl. evidence metadata |
| `get_incident_snapshot` | visual | Fetch a previously attached snapshot image |
| `get_incident_clip` | read | Metadata about a previously attached clip (size, duration, mime) |

**Top-level** (`main.py`):
- `GET /api/health` -- `{"status": "healthy", "version": "2.1.0"}` (no auth)
- FastAPI auto-docs are at `/api-docs` (Swagger) and `/api-redoc` (ReDoc); the OpenAPI schema is at `/api/openapi.json`. The `/docs` URL is owned by the React DocsPage, not Swagger.

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
