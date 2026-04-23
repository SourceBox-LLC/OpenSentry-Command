# AGENTS.md

SourceBox Sentry Command Center — cloud dashboard for managing and viewing security cameras. FastAPI backend + React 19 frontend with Clerk authentication. Live video is streamed through an in-memory segment cache — **no Tigris, no S3, no presigned URLs in the live path**.

## Build & Run

**Prerequisites:** Python ≥ 3.12 (enforced by `backend/pyproject.toml`), Node 18+, `uv` for Python dependency management.

```bash
# Backend
cd backend
uv sync
uv run python start.py              # http://localhost:8000

# Tests
cd backend
uv run pytest

# Frontend
cd frontend
npm install
npm run dev                          # http://localhost:5173
npm run build                        # Production build → backend/static/
```

## Configuration

Backend config is loaded from environment variables (see `backend/.env.example`).

**Required:**
- `CLERK_SECRET_KEY` / `CLERK_PUBLISHABLE_KEY` — Clerk auth

**Optional:**
- `CLERK_WEBHOOK_SECRET` — Svix signature for Clerk subscription webhooks
- `DATABASE_URL` — defaults to `sqlite:///./opensentry.db`
- `FRONTEND_URL` — extra CORS origin (must have scheme, no trailing slash)
- `SEGMENT_CACHE_MAX_PER_CAMERA` — segments cached in memory per camera (default 15, ~30s)
- `SEGMENT_PUSH_MAX_BYTES` — max bytes per pushed segment (default 2 MB)
- `CLEANUP_INTERVAL` — run cache eviction every N playlist updates (default 20)
- `INACTIVE_CAMERA_CLEANUP_HOURS` — free caches for cameras offline this long (default 24)
- `LOG_RETENTION_DAYS` — stream + MCP + audit + motion + notification log retention (default 90)
- `OFFLINE_SWEEP_INTERVAL_SECONDS` — how often to mark stale rows offline (default 30)
- `SENTRY_DSN` — error tracking. In production this is managed by the Fly Sentry extension (`fly ext sentry create -a opensentry-command`) which provisions a sponsored Team plan and auto-injects the secret; you rarely set this by hand. `app/core/sentry.py::init_sentry()` is a no-op when the DSN is absent, so local dev needs no extra config. Dashboard: `fly ext sentry dashboard -a opensentry-command`.

Frontend config: `VITE_CLERK_PUBLISHABLE_KEY`, `VITE_API_URL`, `VITE_LOCAL_HLS`.

## Project Structure

```
backend/
├── app/
│   ├── main.py                   # FastAPI app, CORS, SPA middleware, rate limiting,
│   │                             # log cleanup + offline sweep loops, MCP mount
│   ├── api/
│   │   ├── cameras.py            # Cameras, groups, settings, audit logs, danger zone
│   │   ├── nodes.py              # CloudNode registration, heartbeat, CRUD, plan info
│   │   ├── hls.py                # HLS playlist + segment memory cache + push-segment + HTTP motion fallback
│   │   ├── audit.py              # Stream access logs + stats
│   │   ├── incidents.py          # AI-generated incident reports (CRUD + evidence blobs)
│   │   ├── mcp_keys.py           # MCP API key management + live tool catalog
│   │   ├── mcp_activity.py       # MCP activity logs, stats, SSE stream
│   │   ├── motion.py             # Motion event queries, stats, SSE stream
│   │   ├── notifications.py      # Notification inbox, unread count, SSE, broadcaster
│   │   ├── install.py            # CloudNode + MCP setup script endpoints
│   │   ├── ws.py                 # CloudNode WebSocket channel
│   │   └── webhooks.py           # Clerk subscription webhook handler
│   ├── mcp/
│   │   └── server.py             # FastMCP server + 22 tools + ScopeMiddleware
│   ├── core/
│   │   ├── auth.py               # Clerk JWT validation (V1 + V2 permissions), dependencies
│   │   ├── config.py             # Environment loading (Config class)
│   │   ├── clerk.py              # Clerk SDK init
│   │   ├── database.py           # SQLAlchemy engine + session factory + Base
│   │   └── limiter.py            # slowapi Limiter instance (tenant-aware key)
│   ├── models/models.py          # 13 ORM models (see Data Models below)
│   └── schemas/schemas.py        # Pydantic request/response schemas incl. McpKeyCreate
├── scripts/
│   ├── install.sh / install.ps1  # CloudNode installers (served by install.py)
│   └── mcp-setup.sh / .ps1       # MCP client config helpers (Claude Code / Desktop / Cursor / Windsurf)
├── tests/                        # pytest — security, MCP scoping, motion, notifications, offline sweep
├── start.py                      # Uvicorn entrypoint (0.0.0.0:8000, reload=True)
├── pyproject.toml
└── .env.example

frontend/
└── src/
    ├── pages/
    │   ├── LandingPage.jsx           # Public landing page
    │   ├── DashboardPage.jsx         # Camera grid with status cards + controls
    │   ├── SettingsPage.jsx          # Nodes, groups, recording, danger zone
    │   ├── McpPage.jsx               # MCP keys (scope picker) + activity + incident list
    │   ├── AdminPage.jsx             # Stream logs, MCP activity, audit trail
    │   ├── PricingPage.jsx           # Public pricing tiers
    │   ├── SentinelPage.jsx          # Public marketing page for the Sentinel AI agent
    │   ├── LegalPage.jsx             # /legal/:page — Terms, Privacy, etc.
    │   ├── DocsPage.jsx              # /docs — in-app documentation
    │   ├── SignInPage.jsx / SignUpPage.jsx
    │   └── TestHlsPage.jsx           # Admin-only HLS debug view
    ├── components/
    │   ├── HlsPlayer.jsx             # HLS.js player with Clerk JWT xhrSetup
    │   ├── CameraCard.jsx            # Live thumbnail + status + actions
    │   ├── CameraGridPreview.jsx     # Static preview for the landing page
    │   ├── IncidentReportModal.jsx   # Markdown + evidence viewer
    │   ├── NotificationBell.jsx     # Unread badge + inbox popover (SSE-fed)
    │   ├── AddNodeModal.jsx          # Node creation flow (shows one-time API key)
    │   ├── KeyRotationModal.jsx     # Rotate node API key
    │   ├── UpgradeModal.jsx          # Paywall prompt (plan gating)
    │   ├── HeartbeatBanner.jsx       # "Waiting for first heartbeat" banner shown
    │   │                             # after node creation; polls /api/nodes/{id}
    │   │                             # until it sees a last_seen, persists its
    │   │                             # dismissed state in localStorage
    │   ├── WelcomeHero.jsx           # Dashboard empty-state hero — exports
    │   │                             # AdminWelcomeHero (3-step "set up your first
    │   │                             # camera" checklist) and MemberWelcomeHero
    │   │                             # (capability-focused welcome for non-admins)
    │   ├── Layout.jsx / PublicLayout.jsx
    │   ├── LandingNav.jsx / LandingFooter.jsx
    │   ├── ToastContainer.jsx / LoadingSpinner.jsx
    │   └── EmptyState.jsx
    ├── hooks/
    │   ├── useNotifications.jsx      # SSE inbox + unread count
    │   ├── useMotionAlerts.jsx       # Motion SSE + toast fan-out
    │   ├── usePlanInfo.jsx           # Plan info + node quotas
    │   ├── useSharedToken.jsx        # Shared Clerk token provider (HLS + fetch)
    │   └── useToasts.jsx
    └── services/api.js               # Typed client for every backend endpoint
```

## Architecture

### Request flow

```
Browser ──Clerk JWT──→ FastAPI ──SQL──→ SQLite / PostgreSQL
                          ↕
CloudNode ──X-Node-API-Key──→ FastAPI ──RAM──→ in-memory segment cache
          ──WebSocket──────→                     + per-org motion/notification broadcasters
MCP Client ──Bearer osc_…──→ FastMCP → ScopeMiddleware → tools
```

### Video streaming pipeline

1. CloudNode generates HLS segments via FFmpeg (2-second `.ts` files)
2. CloudNode calls `POST /api/cameras/{id}/push-segment?filename=segment_NNNNN.ts` with the raw `.ts` body and `X-Node-API-Key` header
3. Backend stores the bytes in `_segment_cache[camera_id][filename]`, evicting the oldest once `SEGMENT_CACHE_MAX_PER_CAMERA` is exceeded
4. CloudNode calls `POST /api/cameras/{id}/playlist` with the rolling `stream.m3u8` text
5. Backend rewrites playlist segment filenames to relative `segment/<file>` proxy URLs and caches the result in `_playlist_cache`
6. Browser calls `GET /api/cameras/{id}/stream.m3u8` with JWT → served instantly from `_playlist_cache`
7. Browser fetches each segment via `GET /api/cameras/{id}/segment/{filename}` → served from `_segment_cache` in memory
8. Cache eviction sweeps every `CLEANUP_INTERVAL` playlist updates; the daily cleanup loop flushes caches for cameras offline >`INACTIVE_CAMERA_CLEANUP_HOURS`

### SPA serving

`main.py` SPA middleware:
- `/api/*`, `/ws/*`, `/install.*`, `/mcp-setup.*` → FastAPI handlers
- `POST /mcp` → FastMCP ASGI app (streamable HTTP)
- `GET /mcp` → React `McpPage` (dashboard route)
- `/assets/*` → static files from React build
- Everything else → `index.html` (SPA client-side routing)

`GET /docs` is owned by the React `DocsPage`; FastAPI's auto docs live at `/api-docs` (Swagger) and `/api-redoc` (ReDoc); the OpenAPI schema is at `/api/openapi.json`.

## Authentication

### Clerk JWT (browser users)

`get_current_user()` dependency in `core/auth.py`:
1. Extracts `Authorization: Bearer <token>` header
2. Authenticates with Clerk SDK
3. Extracts `sub` (user_id), `org_id`, and permissions from JWT claims (V1 or V2 format)
4. Returns an `AuthUser` object with `is_admin`, `permissions`, etc.

**V2 permission decoding** (`decode_v2_permissions()`):
- `o` claim contains org object with `fpm` (feature permission map) and `per` (permissions)
- `fea` claim contains feature list (e.g. `o:admin,o:cameras`)
- Decoded to `org:{feature}:{permission}` format

**Dependencies:**
- `require_view()` → any authenticated org member (no extra permission check)
- `require_admin()` → Clerk role `org:admin` / `admin`, or `org:cameras:manage_cameras` permission

### API key (CloudNode)

CloudNode endpoints validate `X-Node-API-Key`:
1. SHA-256 hash the provided key
2. Match against `api_key_hash` on `CameraNode`
3. Derive `org_id` from the matched node row

### MCP API key

MCP endpoint (`POST /mcp`) validates `Authorization: Bearer osc_<hex>`:
1. SHA-256 hash the raw key
2. Match against `McpApiKey.key_hash` with `revoked=False`
3. `ScopeMiddleware` (see below) filters tool discovery + invocation per-key

## Data Models

All 13 models in `backend/app/models/models.py`. Every model has `org_id` for tenant isolation.

| Model | Key Fields | Purpose |
|-------|------------|---------|
| `Camera` | `camera_id`, `node_id` (FK), `name`, `status`, `video_codec`, `audio_codec`, `group_id`, `last_seen` | Camera registered by a CloudNode; `effective_status` flips to offline after a 90s heartbeat gap |
| `CameraNode` | `node_id`, `api_key_hash`, `hostname`, `status`, `video_codec`, `audio_codec`, `last_seen`, `key_rotated_at` | Physical CloudNode device |
| `CameraGroup` | `name`, `color`, `icon` | User-defined camera grouping |
| `Setting` | `key`, `value` | Per-org key/value settings |
| `AuditLog` | `event`, `user_id`, `ip_address`, `details` | Security audit trail |
| `StreamAccessLog` | `user_id`, `camera_id`, `ip_address`, `user_agent`, `accessed_at` | Stream playback audit |
| `McpApiKey` | `name`, `key_hash`, `scope_mode`, `scope_tools` (JSON text), `last_used_at`, `revoked` | MCP API keys — **scope_mode**: `all` / `readonly` / `custom` |
| `McpActivityLog` | `tool_name`, `key_name`, `status`, `duration_ms`, `args_summary`, `error`, `timestamp` | Per-call MCP audit log |
| `Incident` | `title`, `summary`, `report` (markdown), `severity`, `status`, `camera_id`, `created_by`, `resolved_at`, `resolved_by` | AI-generated incident (`open` / `acknowledged` / `resolved` / `dismissed`) |
| `IncidentEvidence` | `incident_id` (FK cascade), `kind` (`snapshot` / `clip` / `observation`), `text`, `camera_id`, `data` (LargeBinary), `data_mime` | Snapshot JPEG, clip (MPEG-TS bytes), or text observation — evidence travels inline with the incident |
| `MotionEvent` | `camera_id`, `node_id`, `score` (0–100), `segment_seq`, `timestamp` | Motion detected by CloudNode scene-change analysis |
| `Notification` | `kind`, `audience` (`all` / `admin`), `title`, `body`, `severity`, `link`, `camera_id`, `node_id`, `meta_json` | Unified inbox entry (motion, camera/node online/offline, errors) |
| `UserNotificationState` | `clerk_user_id` + `org_id` (unique), `last_viewed_at` | Per-user read cursor for the inbox |

Validation constants (also in `models.py`):
- `INCIDENT_STATUSES` = `("open", "acknowledged", "resolved", "dismissed")`
- `INCIDENT_SEVERITIES` = `("low", "medium", "high", "critical")`

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
| `motion.py` | `/api/motion` | motion |
| `notifications.py` | `/api/notifications` | notifications |
| `install.py` | (none) | installation |
| `ws.py` | (none) | ws |
| `webhooks.py` | `/api/webhooks` | webhooks |

### All endpoints

**cameras.py** (prefix `/api`):
- `GET /cameras` — list cameras (view)
- `GET /cameras/{camera_id}` — get camera (view)
- `POST /cameras/{camera_id}/snapshot` — ask node to capture & store a snapshot locally (view)
- `POST /cameras/{camera_id}/recording` — start/stop recording on the node (view)
- `POST /cameras/{camera_id}/codec` — CloudNode reports codec after first segment (node API key, 30/min)
- `GET /camera-groups` — list groups (view)
- `POST /camera-groups` — create group (admin)
- `DELETE /camera-groups/{group_id}` — delete group (admin)
- `PUT /cameras/{camera_id}/group` — assign group (admin)
- `GET /settings` — all settings (view)
- `GET /settings/recording` — recording settings (view)
- `POST /settings/recording` — update recording settings (admin)
- `GET /audit-logs` — audit logs (admin)
- `POST /settings/danger/wipe-logs` — permanently delete all stream + MCP + audit logs (admin + Pro/Business)
- `POST /settings/danger/full-reset` — wipe all nodes/cameras/logs/settings for the org (admin + Pro/Business)

**nodes.py** (prefix `/api/nodes`):
- `POST /validate` — validate node_id + API key pair, used by CloudNode setup wizard (10/min)
- `POST /register` — CloudNode registration (API key, 10/min)
- `POST /heartbeat` — CloudNode heartbeat (API key, 60/min)
- `GET /` — list nodes (admin)
- `GET /plan` — current plan, node usage, and limits (view)
- `POST /` — create node (admin, requires active billing + plan capacity)
- `GET /ws-status` — which nodes are WebSocket-connected (admin)
- `GET /{node_id}` — get node (admin)
- `DELETE /{node_id}` — delete node (admin; cascades cameras + flushes segment caches)
- `POST /{node_id}/rotate-key` — rotate API key (admin, 5/min)

**hls.py** (prefix `/api/cameras/{camera_id}`):
- `GET /stream.m3u8` — HLS playlist served from cache (JWT)
- `GET /segment/{filename}` — serve cached `.ts` segment from memory (JWT)
- `POST /push-segment?filename=…` — CloudNode pushes `.ts` segment into cache (API key, 1200/min)
- `POST /playlist` — update playlist (API key, 600/min)
- `POST /motion` — HTTP fallback for motion events when WebSocket is offline (API key, 120/min)

**audit.py** (prefix `/api`):
- `GET /audit/stream-logs` — stream access logs (admin)
- `GET /audit/stream-logs/stats` — aggregates by camera/user/day (admin)

**incidents.py** (prefix `/api/incidents`):
- `GET /` — list (admin; filters: `status`, `severity`, `camera_id`, `limit`, `offset`)
- `GET /counts` — aggregate counts (admin)
- `GET /{incident_id}` — detail with evidence list (admin)
- `PATCH /{incident_id}` — update status / severity / summary / report (admin)
- `DELETE /{incident_id}` — delete incident + cascade evidence (admin)
- `GET /{incident_id}/evidence/{evidence_id}` — stream snapshot or clip blob (admin)
- `GET /{incident_id}/evidence/{evidence_id}/playlist.m3u8` — synthetic single-segment HLS playlist for in-dashboard clip playback (admin)

**mcp_keys.py** (prefix `/api/mcp`):
- `POST /keys` — generate key; JSON body `{name, scopeMode, scopeTools?}`; returns plaintext `osc_...` once (admin + active billing)
- `GET /tools` — live tool catalog with read/write kind (admin)
- `GET /keys` — list MCP keys for the org (admin)
- `DELETE /keys/{key_id}` — revoke (admin)

**mcp_activity.py** (prefix `/api/mcp/activity`):
- `GET /stream` — SSE stream of live MCP tool calls (admin)
- `GET /recent` — recent tool calls (admin)
- `GET /sessions` — session summaries (admin)
- `GET /stats` — aggregated stats by tool / key / time (admin)
- `GET /logs` — filterable MCP tool call log (admin)
- `GET /logs/stats` — summary counts for logs (admin)

**motion.py** (prefix `/api/motion`):
- `GET /events` — list motion events; filters: `camera_id`, `hours`, `limit`, `offset` (view)
- `GET /events/stats` — per-camera aggregates (view)
- `GET /events/stream` — SSE motion feed for dashboard notifications (view)

**notifications.py** (prefix `/api/notifications`):
- `GET /` — paginated inbox, newest first; applies audience filter (view)
- `GET /unread-count` — cheap count for the bell badge (capped at 99) (view)
- `POST /mark-viewed` — bump `last_viewed_at` to now (view)
- `GET /stream` — SSE stream for the bell; audience filter applied server-side (view)

**install.py** (no prefix, no auth):
- `GET /install.sh` / `GET /install.ps1` — CloudNode installer scripts
- `GET /mcp-setup.sh` / `GET /mcp-setup.ps1` — MCP client config helpers

**ws.py** (no prefix):
- `WS /ws/node` — WebSocket channel for CloudNode realtime (API key in query)
  - Node → Backend: `heartbeat`, `command_result`, `event`
  - Backend → Node: `ack`, `command`, `error`
  - Event payloads include `motion_detected` (camera_id, score, timestamp, segment_seq)

**webhooks.py** (prefix `/api/webhooks`):
- `POST /clerk` — Clerk subscription events (Svix signature when `CLERK_WEBHOOK_SECRET` is set)

**Top-level** (`main.py`):
- `GET /api/health` — `{"status": "healthy", "version": "2.1.0"}` (no auth)
- FastAPI docs: `/api-docs` (Swagger), `/api-redoc` (ReDoc), OpenAPI at `/api/openapi.json`. `/docs` is the React `DocsPage`.

## MCP Server

Mounted at `/mcp` via FastMCP streamable HTTP. Authenticates with `Authorization: Bearer osc_...` against `McpApiKey.key_hash`. Exposes **22 tools** (16 read + 6 write).

### Scope middleware

`ScopeMiddleware` (in `app/mcp/server.py`) runs before every `list_tools` and `call_tool` request:

1. Extracts the Bearer token from request headers via `get_http_headers()`
2. SHA-256-hashes the key and looks up the matching `McpApiKey` row
3. Computes the allowed-tool frozenset from `scope_mode` + `scope_tools`
4. Filters `list_tools` responses and raises `ToolError` on disallowed `call_tool` invocations

Scope modes:
- `"all"` (default; NULL also treated as "all" for legacy rows) → every tool
- `"readonly"` → intersection with `MCP_READ_TOOLS` (16 tools)
- `"custom"` → intersection of `scope_tools` JSON list with `MCP_ALL_TOOLS` (unknown names silently dropped — can't accidentally enable a new server-side WRITE tool via typo)

### Tool inventory

**Read tools (`MCP_READ_TOOLS`, 16):**

| Tool | Purpose |
|------|---------|
| `list_cameras` | All cameras with status/codec/group |
| `get_camera` | One camera by id |
| `get_stream_url` | Authenticated HLS URL for a camera |
| `view_camera` | Live JPEG from a camera (agent can see it) |
| `watch_camera` | Multi-frame burst (2–10 frames, 1–30s apart) |
| `list_camera_groups` | Camera groups for the org |
| `list_nodes` | CloudNodes + their status |
| `get_node` | One node by id |
| `get_recording_settings` | Current recording config |
| `get_stream_logs` | Stream access audit entries |
| `get_stream_stats` | Aggregated views by camera/user/day |
| `get_system_status` | Org-wide snapshot (cameras on/offline, plan, nodes) |
| `list_incidents` | Previous incidents (filter by status/severity/camera) |
| `get_incident` | Full detail of one incident incl. evidence metadata |
| `get_incident_snapshot` | Fetch a previously attached snapshot JPEG |
| `get_incident_clip` | Metadata about a previously attached clip |

**Write tools (`MCP_WRITE_TOOLS`, 6):**

| Tool | Purpose |
|------|---------|
| `create_incident` | Open a new incident (title, summary, severity) |
| `add_observation` | Append a text observation to an incident |
| `attach_snapshot` | Capture a JPEG and attach it as evidence |
| `attach_clip` | Save the recent live buffer as a video clip (pulls from in-memory HLS cache) |
| `update_incident` | Change status / severity / summary / report body (revisions) |
| `finalize_incident` | Write the markdown report body for the first time |

## CORS

Configured in `main.py`:
```python
cors_origins = [
    "http://localhost:5173",
    "http://localhost:8000",
    "https://opensentry-command.fly.dev",
]
```
Plus `FRONTEND_URL` if set (validated: must have scheme, no trailing slash, no embedded whitespace). All methods and headers allowed; credentials allowed.

## Rate Limiting

`slowapi` with a tenant-aware key:
- `POST /api/nodes/validate`, `POST /api/nodes/register` — 10/min
- `POST /api/nodes/heartbeat` — 60/min
- `POST /api/nodes/{id}/rotate-key` — 5/min
- `POST /api/cameras/{id}/codec` — 30/min
- `POST /api/cameras/{id}/push-segment` — 1200/min
- `POST /api/cameras/{id}/playlist` — 600/min
- `POST /api/cameras/{id}/motion` — 120/min

HLS `GET` paths (`stream.m3u8`, `segment/{file}`) are intentionally unlimited — segment fetches are fast-path with no per-request DB work.

## Webhook Handling

`POST /api/webhooks/clerk` handles Clerk subscription events:
- Verifies signature with Svix when `CLERK_WEBHOOK_SECRET` is set; accepts unsigned JSON otherwise (dev mode)
- On `subscription.{created,updated,active}` — writes `Setting(org_plan)`, updates the Clerk org member limit, and runs `enforce_camera_cap` so a plan change (in either direction) flips the `Camera.disabled_by_plan` flags to match the new cap.
- On `subscription.pastDue` / `subscriptionItem.pastDue` — writes `Setting(payment_past_due="true")` and a timestamped `payment_past_due_at`. No camera enforcement at this stage; see the grace-period note below.
- On `paymentAttempt.updated` with `status="paid"` — clears both past-due settings and re-runs `enforce_camera_cap`, so cameras suspended during a grace-expired past-due window light back up.
- On `subscriptionItem.{canceled,ended}` — reverts to `free_org`, resets member limit, and re-runs `enforce_camera_cap`. Camera rows are preserved (not deleted) so re-subscribe instantly restores streaming.
- On `organization.deleted` — full wipe.

## Plan Enforcement

`app/core/plans.py` owns plan-cap policy. Two entry points:

- `resolve_org_plan(db, org_id)` — nominal plan (what Clerk says the org pays for). Fast-path reads `Setting(org_plan)`; falls back to a throttled `clerk.organizations.get_billing_subscription` call for free/missing orgs. Used for the status-bar badge CloudNode shows the operator.
- `effective_plan_for_caps(db, org_id)` — plan to use for *cap enforcement*. Returns `resolve_org_plan` unless the org has been `payment_past_due` for more than `PAYMENT_GRACE_DAYS` (7), in which case it returns `"free_org"`. Used inside `enforce_camera_cap`; keeps the two concerns separate so brief card failures don't punish paying users but long-unpaid accounts don't keep getting Pro service.

`enforce_camera_cap(db, org_id)` — idempotent. Orders the org's cameras by `created_at ASC`, keeps the oldest N (N = effective plan's `max_cameras`), flags the rest as `disabled_by_plan=True`. Oldest-first is deterministic and preserves long-running cameras with history. On upgrade, flags clear in the same call.

**Triggers** for `enforce_camera_cap`:
1. Webhook: subscription lifecycle events (create/update/cancel/paid).
2. Register (`POST /api/nodes/register`): safety net for any missed webhook. Idempotent so cost is just one indexed query in the steady state.
3. Heartbeat (`POST /api/nodes/heartbeat`): gated on `payment_past_due=="true"`. Drives the time-based grace-expiration transition since no webhook fires for that clock tick.

**Push-segment gate** (`POST /api/cameras/{id}/push-segment`): when `camera.disabled_by_plan` is set, returns **HTTP 402** with a structured `plan_limit_hit` body (plan display name, cap, camera name, upgrade copy). CloudNode treats 402 as non-retryable and surfaces the suspension in its TUI.

**Heartbeat response** also carries `disabled_cameras: list[str]` scoped to the calling node, so CloudNode can skip the upload task entirely for suspended cameras (no 402 flood) and mark those rows `suspended (plan)` in its live dashboard.

## Background Loops

`main.py` starts two long-running tasks on lifespan startup:

| Task | Cadence | What it does |
|------|---------|--------------|
| `_log_cleanup_loop` | Every `LOG_CLEANUP_INTERVAL_HOURS` (hours) | Deletes logs older than `LOG_RETENTION_DAYS` (stream, MCP, audit, motion, notification); flushes in-memory segment/playlist caches for cameras offline >`INACTIVE_CAMERA_CLEANUP_HOURS` |
| `_offline_sweep_loop` | Every `OFFLINE_SWEEP_INTERVAL_SECONDS` (30s) | Flips nodes/cameras whose `last_seen` is older than 90s from `status='online'` to `'offline'` and emits `Notification` rows + broadcasts SSE events |

## Key Patterns

**Tenant isolation:** every query filters by `org_id` from the authenticated user/node.

**Error handling:** FastAPI `HTTPException` with appropriate status codes. Clerk auth failures return 401/403.

**Database sessions:** `get_db()` dependency yields a SQLAlchemy session per request.

**In-memory segment cache:** live `.ts` segments live in `_segment_cache` (a `dict[camera_id, dict[filename, (bytes, ts)]]`) inside `hls.py`. Backend never touches S3 for live video. Recordings and snapshots live on the CloudNode. Incident snapshots + clips are stored inline on `IncidentEvidence.data` (LargeBinary).

**Codec detection:** CloudNode reports codec via `POST /api/cameras/{id}/codec` after the first segment. Stored on the Camera row and injected into HLS playlists as `#EXT-X-CODECS`.

**Notification broadcaster:** `notification_broadcaster` (in `notifications.py`) is a per-process pub/sub — SSE subscribers register per org + admin flag; `emit_camera_transition`, `emit_node_transition`, and motion event handlers write a `Notification` row then broadcast.

**Motion broadcaster:** the motion SSE stream pushes events from either the WebSocket channel (`/ws/node`) or the HTTP fallback (`POST /api/cameras/{id}/motion`).

**Shared Clerk token:** frontend's `useSharedToken` serialises the Clerk JWT for HLS.js's `xhrSetup` so segment fetches ride on the same auth as API calls.

**First-heartbeat UX:** when the admin creates a node, the dashboard stashes the new `node_id` in `localStorage` and `HeartbeatBanner` starts polling `GET /api/nodes/{node_id}` every few seconds. As soon as `last_seen` is non-null the banner auto-dismisses. Users don't have to refresh — it's a reassurance loop for the 30–60s window where the node is downloading ffmpeg / registering cameras.

**Role-split welcome hero:** `WelcomeHero.jsx` exports two components — `AdminWelcomeHero` shows the "Install a CloudNode → Camera goes live" checklist with CTAs into Settings + the install guide; `MemberWelcomeHero` shows a capability-focused welcome (live monitoring, motion alerts, team workspace) because members can't act on a setup checklist. `DashboardPage` picks the right one based on `is_admin`.

## Setup Scripts

`backend/scripts/mcp-setup.sh` + `mcp-setup.ps1` are served verbatim from `install.py`. They:
1. Accept `<api_key> <server_url>` (positional)
2. Detect installed MCP clients (Claude Code, Claude Desktop, Cursor, Windsurf)
3. Prompt the user for which ones to configure
4. Merge an `opensentry` entry into each client's JSON config (creating directories + backing up corrupted files)

**Windows invocation pattern** — `irm … | iex -Args …` **does not work** (`iex` has no `-Args`). Use the scriptblock pattern instead, which is what the dashboard prints:

```powershell
& ([scriptblock]::Create((irm <url>/mcp-setup.ps1))) '<api_key>' '<server_url>'
```

**Bash invocation** — when run via `curl … | bash -s --`, stdin is the piped script, so `read` would hit EOF immediately. The script falls back to `</dev/tty` when stdin isn't a TTY.

## Key Dependencies

- `fastapi` / `uvicorn` — Web framework and ASGI server
- `fastmcp` — Model Context Protocol server (streamable HTTP)
- `sqlalchemy` — ORM (SQLite dev, PostgreSQL production)
- `pydantic` — Request/response validation
- `clerk-backend-api` — Clerk authentication
- `pyjwt` — JWT token handling (for V2 permission decoding)
- `slowapi` — Rate limiting
- `httpx` — HTTP client
- `svix` — Webhook signature verification
- `python-dotenv` — Environment variable loading

## Development Notes

- Database tables auto-created on startup via `Base.metadata.create_all()`
- Backend serves the React build as static files in production (SPA middleware in `main.py`)
- Frontend uses HLS.js for video playback with a Clerk JWT injected via `xhrSetup`
- `VITE_LOCAL_HLS=true` bypasses the backend and streams directly from CloudNode on localhost:8080 (for local dev only)
- Tests live in `backend/tests/` and run with `uv run pytest`; scope middleware has dedicated coverage (`test_mcp_keys.py`)
