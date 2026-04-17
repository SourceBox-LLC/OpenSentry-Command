<p align="center">
  <h1 align="center">OpenSentry Command Center</h1>
  <p align="center">
    Cloud dashboard for managing and viewing your security cameras in real time.
    <br />
    <a href="https://opensentry-command.fly.dev">Live App</a>
    &middot;
    <a href="#quick-start">Quick Start</a>
    &middot;
    <a href="#api-reference">API Reference</a>
    &middot;
    <a href="https://github.com/SourceBox-LLC/OpenSentry-CloudNode">CloudNode</a>
  </p>
</p>

<p align="center">
  <a href="https://www.gnu.org/licenses/agpl-3.0"><img src="https://img.shields.io/badge/License-AGPL_v3-blue.svg" alt="License: AGPL v3"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Backend-FastAPI_2.1-009688.svg" alt="FastAPI"></a>
  <a href="https://react.dev/"><img src="https://img.shields.io/badge/Frontend-React_19-61DAFB.svg" alt="React"></a>
</p>

---

OpenSentry Command Center is the cloud hub for the OpenSentry ecosystem. It receives live HLS video streams from [CloudNode](https://github.com/SourceBox-LLC/OpenSentry-CloudNode) devices on your local network, caches segments in memory, and proxies them to any browser. Authentication and multi-tenant isolation are handled by Clerk.

**What it does:**
- Receives live HLS video from CloudNode devices and proxies it to the browser via a same-origin in-memory cache — no object store, no presigned URLs
- Manages camera nodes and groups, with per-org Clerk authentication
- Multi-tenant with organization-based access control (V2 JWT permissions)
- Motion detection events from CloudNodes with per-camera aggregates and a live SSE feed
- Unified notification inbox for motion, camera/node status transitions, and errors
- Audit logging for stream access, admin actions, and MCP tool calls
- MCP server exposing 22 tools (16 read, 6 write) so AI clients can view cameras, file incident reports with snapshots and short video clips, and read back past investigations — with per-key scoping (all / readonly / custom allow-list)

---

## Quick Start

### Prerequisites

- **Python** 3.12+ (backend declares `requires-python = ">=3.12"` in `pyproject.toml`)
- **Node.js** 18+
- **uv** ([Python package manager](https://docs.astral.sh/uv/))

### 1. Backend

```bash
cd backend
cp .env.example .env    # Edit with your Clerk keys
uv sync
uv run python start.py
```

API available at `http://localhost:8000`

### 2. Frontend

```bash
cd frontend
cp .env.example .env    # Set VITE_CLERK_PUBLISHABLE_KEY
npm install
npm run dev
```

App available at `http://localhost:5173`

### 3. Connect a CloudNode

Create a camera node from the Settings page, then run [CloudNode](https://github.com/SourceBox-LLC/OpenSentry-CloudNode) with those credentials. Cameras auto-register when the CloudNode first connects.

### 4. Connect an MCP client (optional)

From the MCP page, generate an API key and pick a scope (all / readonly / custom). The page prints a one-line installer that configures Claude Code, Claude Desktop, Cursor, or Windsurf in place:

```bash
# Linux / macOS
curl -fsSL https://opensentry-command.fly.dev/mcp-setup.sh | bash -s -- <api_key> <mcp_url>

# Windows (PowerShell)
& ([scriptblock]::Create((irm https://opensentry-command.fly.dev/mcp-setup.ps1))) '<api_key>' '<mcp_url>'
```

The scripts detect which clients you already have and merge an `opensentry` entry into each one's MCP config.

---

## Architecture

```
   CloudNode (Rust)                  Command Center                    Browser
  ┌──────────────┐            ┌───────────────────────┐         ┌──────────────┐
  │ USB Camera   │            │  FastAPI Backend      │         │  React 19    │
  │      ↓       │            │                       │         │              │
  │ FFmpeg (HLS) │──push─────→│  In-memory segment    │←─GET───→│  HLS.js      │
  │              │  segments  │  cache (~60 segs/cam) │  proxy  │  (video)     │
  │              │──register─→│  SQLite / PostgreSQL  │  URLs   │              │
  │              │──heartbeat→│  Clerk Auth           │←─JWT───→│  Clerk Auth  │
  │              │──WS events │  FastMCP (/mcp)       │←──SSE───│  Motion feed │
  └──────────────┘            └───────────────────────┘         └──────────────┘
```

**Video pipeline:** CloudNode transcodes USB camera video into HLS segments and pushes each `.ts` file directly to the backend via `POST /api/cameras/{id}/push-segment`. The backend caches segments in memory (60 per camera by default, ~60s buffer) and serves them through the same-origin proxy at `GET /api/cameras/{id}/segment/{file}`. The rewritten playlist contains relative segment URLs, so the browser's Clerk JWT auth header is automatically attached. No S3, no presigned URLs, no third-party storage in the live path.

**Authentication:** Clerk handles user sign-up, login, and organization management. The backend validates JWT tokens (V1 and V2 permission formats) and extracts organization-scoped permissions. CloudNodes authenticate with API keys (SHA-256 hashed in the database) passed via `X-Node-API-Key`. MCP clients authenticate with `Authorization: Bearer osc_...` keys (also hashed).

**Storage:** Live segments live in the backend's in-memory cache; they expire automatically once `SEGMENT_CACHE_MAX_PER_CAMERA` is exceeded. Recordings and snapshots live on the CloudNode itself in its encrypted SQLite database. SQLite is used for development on the Command Center (`opensentry.db`); PostgreSQL for production. Incident snapshots and clips are stored inline on `IncidentEvidence.data` (LargeBinary) — evidence travels with the incident.

**Real-time:** CloudNodes maintain a WebSocket channel (`/ws/node`) used for commands, status, and motion events. The dashboard subscribes to SSE feeds for motion events (`/api/motion/events/stream`), notifications (`/api/notifications/stream`), and MCP activity (`/api/mcp/activity/stream`).

---

## Configuration

### Backend environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CLERK_SECRET_KEY` | Yes | | Clerk backend API key |
| `CLERK_PUBLISHABLE_KEY` | Yes | | Clerk frontend key |
| `CLERK_WEBHOOK_SECRET` | No | | Svix signature secret for Clerk webhooks |
| `DATABASE_URL` | No | `sqlite:///./opensentry.db` | SQLAlchemy connection string |
| `FRONTEND_URL` | No | `http://localhost:5173` | Extra CORS origin (must include scheme, no trailing slash) |
| `SEGMENT_CACHE_MAX_PER_CAMERA` | No | `60` | Segments cached in memory per camera (~1s each) |
| `SEGMENT_PUSH_MAX_BYTES` | No | `2097152` | Max bytes per pushed segment (2 MB) |
| `CLEANUP_INTERVAL` | No | `20` | Run cache eviction every N playlist updates |
| `INACTIVE_CAMERA_CLEANUP_HOURS` | No | `24` | Free caches for cameras offline this long |
| `LOG_RETENTION_DAYS` | No | `90` | Stream, MCP, audit, motion, and notification log retention |
| `OFFLINE_SWEEP_INTERVAL_SECONDS` | No | `30` | How often to flip stale `online` rows to `offline` |
| `REDIS_URL` | No | (empty) | Redis connection for rate limiter storage; in-memory fallback when unset (fine for single-instance, but limits don't hold across VMs) |
| `SENTRY_DSN` | No | (empty) | Sentry error tracking DSN; leave blank to disable (no-ops gracefully) |
| `SENTRY_TRACES_SAMPLE_RATE` | No | `0.1` | Sentry performance trace sample rate (0.0–1.0) |

### Frontend environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_CLERK_PUBLISHABLE_KEY` | Yes | Clerk publishable key |
| `VITE_API_URL` | No | Backend URL (default: `http://localhost:8000`) |
| `VITE_LOCAL_HLS` | No | Set `true` to stream directly from CloudNode on localhost |

---

## API Reference

### Cameras

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/cameras` | User | List all cameras |
| GET | `/api/cameras/{camera_id}` | User | Get camera details |
| POST | `/api/cameras/{camera_id}/snapshot` | User | Ask the node to capture a snapshot locally |
| POST | `/api/cameras/{camera_id}/recording` | User | Start/stop recording on the node |
| POST | `/api/cameras/{camera_id}/codec` | Node | Report video/audio codec (called by CloudNode, 30/min) |

### Camera Groups

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/camera-groups` | User | List groups |
| POST | `/api/camera-groups` | Admin | Create group |
| DELETE | `/api/camera-groups/{group_id}` | Admin | Delete group |
| PUT | `/api/cameras/{camera_id}/group` | Admin | Assign camera to a group |

### Camera Nodes

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/nodes` | Admin | List all nodes |
| POST | `/api/nodes` | Admin | Create a node (requires active billing + plan capacity) |
| GET | `/api/nodes/{node_id}` | Admin | Get node details |
| DELETE | `/api/nodes/{node_id}` | Admin | Delete node (cascades cameras + segment caches) |
| POST | `/api/nodes/{node_id}/rotate-key` | Admin | Rotate API key (5/min) |
| GET | `/api/nodes/plan` | User | Current plan, node usage, and limits |
| GET | `/api/nodes/ws-status` | Admin | Which org nodes are currently WebSocket-connected |
| POST | `/api/nodes/validate` | None | Validate a `(node_id, api_key)` pair (used by CloudNode setup wizard, 10/min) |
| POST | `/api/nodes/register` | Node | CloudNode registration (10/min) |
| POST | `/api/nodes/heartbeat` | Node | CloudNode heartbeat (60/min) |

### HLS Streaming

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/cameras/{camera_id}/stream.m3u8` | User | HLS playlist (cached, with relative segment URLs) |
| GET | `/api/cameras/{camera_id}/segment/{file}` | User | Serve cached `.ts` segment from memory |
| POST | `/api/cameras/{camera_id}/push-segment` | Node | Push a `.ts` segment into the cache (1200/min) |
| POST | `/api/cameras/{camera_id}/playlist` | Node | Update playlist (600/min) |
| POST | `/api/cameras/{camera_id}/motion` | Node | HTTP fallback for motion events when WebSocket is offline (120/min) |

### Settings

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/settings` | User | All settings |
| GET | `/api/settings/recording` | User | Recording settings |
| POST | `/api/settings/recording` | Admin | Update recording settings |
| POST | `/api/settings/danger/wipe-logs` | Admin | Permanently delete all stream + MCP + audit logs (Pro/Business only) |
| POST | `/api/settings/danger/full-reset` | Admin | Wipe all nodes, cameras, logs, and settings for the org (Pro/Business only) |

### Audit

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/audit-logs` | Admin | List audit logs |
| GET | `/api/audit/stream-logs` | Admin | Stream access logs |
| GET | `/api/audit/stream-logs/stats` | Admin | Stream access stats grouped by camera/user/day |

### Incident Reports

Agents author incidents via the MCP write tools below; admins review them from the dashboard's Incidents view.

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/incidents` | Admin | List incidents (filter by `status`, `severity`, `camera_id`) |
| GET | `/api/incidents/counts` | Admin | Aggregate counts (open, open critical, open high, total) |
| GET | `/api/incidents/{incident_id}` | Admin | Incident detail + all evidence metadata |
| PATCH | `/api/incidents/{incident_id}` | Admin | Acknowledge / resolve / dismiss / edit |
| DELETE | `/api/incidents/{incident_id}` | Admin | Delete incident (cascades to evidence blobs) |
| GET | `/api/incidents/{incident_id}/evidence/{evidence_id}` | Admin | Stream a snapshot or clip blob |
| GET | `/api/incidents/{incident_id}/evidence/{evidence_id}/playlist.m3u8` | Admin | Synthetic single-segment HLS playlist for in-dashboard clip playback |

### Motion Events

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/motion/events` | User | List motion events (filter: `camera_id`, `hours`, `limit`, `offset`) |
| GET | `/api/motion/events/stats` | User | Per-camera aggregates: event count, peak score, latest |
| GET | `/api/motion/events/stream` | User | SSE stream — real-time motion alerts for the dashboard |

### Notifications

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/notifications` | User | Paginated inbox (motion, camera/node online/offline, errors) |
| GET | `/api/notifications/unread-count` | User | Unread badge count (capped at 99) |
| POST | `/api/notifications/mark-viewed` | User | Mark the whole inbox viewed |
| GET | `/api/notifications/stream` | User | SSE stream for live bell updates |

### MCP (for AI clients)

Streamable HTTP MCP server exposing **22 tools** (16 read + 6 write). Requires a Pro or Business plan + an API key generated from the dashboard. Each key has a scope (`all` / `readonly` / `custom`) enforced server-side by a middleware layer — agents never see or can invoke tools the key isn't scoped for.

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/mcp` | MCP Key | Streamable HTTP MCP endpoint (`Authorization: Bearer osc_...`) |
| GET | `/api/mcp/keys` | Admin | List MCP API keys |
| POST | `/api/mcp/keys` | Admin | Generate a new key (shown once; body: `{name, scopeMode, scopeTools?}`) |
| DELETE | `/api/mcp/keys/{key_id}` | Admin | Revoke a key |
| GET | `/api/mcp/tools` | Admin | Live tool catalog (name, description, read/write kind) |
| GET | `/api/mcp/activity/stream` | Admin | SSE stream of live MCP tool calls |
| GET | `/api/mcp/activity/recent` | Admin | Recent MCP tool calls |
| GET | `/api/mcp/activity/sessions` | Admin | MCP session summaries |
| GET | `/api/mcp/activity/stats` | Admin | Aggregated stats by tool / key / time |
| GET | `/api/mcp/activity/logs` | Admin | MCP tool call activity log (filterable) |
| GET | `/api/mcp/activity/logs/stats` | Admin | Summary counts for MCP logs |

See [AGENTS.md](AGENTS.md) for the full per-tool list.

### Installers (no auth)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/install.sh` / `/install.ps1` | CloudNode installer scripts |
| GET | `/mcp-setup.sh` / `/mcp-setup.ps1` | MCP client setup helpers |
| GET | `/downloads/{os}/{arch}` | 302 redirect to the latest CloudNode binary on GitHub Releases (os: `linux`/`macos`/`windows`, arch: `x86_64`/`aarch64`/`armv7`) |

### System

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/health` | None | Health check |
| POST | `/api/webhooks/clerk` | Webhook | Clerk subscription events (Svix-signed) |
| WS | `/ws/node` | Node (query) | CloudNode real-time channel (heartbeat, commands, motion) |

**Auth types:** `User` = Clerk JWT, `Admin` = Clerk JWT with admin permission, `Node` = `X-Node-API-Key` header, `MCP Key` = `Authorization: Bearer osc_...`.

---

## Permissions

Access control uses Clerk organizations with V1 or V2 JWT permission claims:

| Check | Grants |
|-------|--------|
| Clerk role `org:admin` / `admin` | Full access (nodes, groups, settings, audit logs, incidents, MCP keys) |
| `org:cameras:manage_cameras` permission | Manage cameras and nodes (alternative admin path) |
| Any authenticated org member | View cameras, streams, motion, notifications |

Admin access is required for node management, group management, settings, audit logs, incident review, MCP key management, and danger-zone operations. All authenticated org members can view cameras, streams, motion events, and their notification inbox.

---

## Data Models

All 13 ORM models live in `backend/app/models/models.py`; every row is scoped by `org_id`.

| Model | Purpose |
|-------|---------|
| `Camera` | Camera device registered by a CloudNode; tracks codec, status, group |
| `CameraNode` | Physical CloudNode device; holds `api_key_hash` + codec info |
| `CameraGroup` | User-defined grouping (name, color, icon) |
| `Setting` | Per-org key/value store (e.g. recording config) |
| `AuditLog` | Admin / security-relevant audit trail |
| `StreamAccessLog` | Per-stream playback audit (user, IP, UA) |
| `McpApiKey` | Hashed MCP API key + scope (`scope_mode`, `scope_tools`) |
| `McpActivityLog` | Per-call MCP audit entry (tool, status, duration, args summary) |
| `Incident` | AI-generated incident report (open / acknowledged / resolved / dismissed) |
| `IncidentEvidence` | Inline snapshot, clip (MPEG-TS blob), or text observation attached to an incident |
| `MotionEvent` | Motion detection event reported by a node (`score`, `segment_seq`, timestamp) |
| `Notification` | Unified inbox entry (motion, camera/node online/offline, errors) |
| `UserNotificationState` | Per-`(clerk_user_id, org_id)` read cursor (`last_viewed_at`) |

---

## Project Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI app, CORS, SPA middleware, cleanup + offline sweep loops
│   ├── api/
│   │   ├── cameras.py           # Cameras, groups, settings, audit logs, danger zone
│   │   ├── nodes.py             # CloudNode registration, heartbeat, CRUD, plan info
│   │   ├── hls.py               # HLS playlist + in-memory segment cache + push-segment + HTTP motion fallback
│   │   ├── audit.py             # Stream access logging
│   │   ├── incidents.py         # AI-generated incident reports (CRUD + evidence blobs)
│   │   ├── mcp_keys.py          # MCP key management + tool catalog
│   │   ├── mcp_activity.py      # MCP tool call logs, stats, SSE stream
│   │   ├── motion.py            # Motion events: queries, stats, SSE stream
│   │   ├── notifications.py     # Notification inbox + unread + SSE + broadcaster
│   │   ├── install.py           # CloudNode + MCP setup scripts
│   │   ├── ws.py                # WebSocket channel (heartbeat, commands, motion events)
│   │   └── webhooks.py          # Clerk subscription webhooks
│   ├── mcp/
│   │   ├── server.py            # FastMCP server + 22 tools + ScopeMiddleware
│   │   └── activity.py          # MCP activity tracking + per-org broadcasting
│   ├── core/
│   │   ├── auth.py              # Clerk JWT validation (V1 + V2), dependencies
│   │   ├── audit.py             # Audit log helper (records admin actions)
│   │   ├── codec.py             # Video codec string sanitization
│   │   ├── config.py            # Environment loading (Config class)
│   │   ├── clerk.py             # Clerk SDK initialization
│   │   ├── database.py          # SQLAlchemy engine + session factory
│   │   ├── limiter.py           # slowapi Limiter instance (tenant-aware key)
│   │   ├── migrations.py        # Manual schema migrations (stand-in for Alembic)
│   │   ├── plans.py             # Plan limit logic (node quotas per tier)
│   │   ├── sentry.py            # Sentry error tracking initialization
│   │   └── versions.py          # CloudNode version compatibility checking
│   ├── models/models.py         # 13 ORM models (see table above)
│   └── schemas/schemas.py       # Pydantic request/response schemas
├── scripts/
│   ├── install.sh / install.ps1 # CloudNode installers
│   └── mcp-setup.sh / .ps1      # MCP client config helpers
├── tests/                       # pytest (security + MCP scoping + motion + notifications)
├── .env.example
├── pyproject.toml
└── start.py                     # Uvicorn entry point

frontend/
└── src/
    ├── pages/
    │   ├── LandingPage.jsx         # Public landing page
    │   ├── DashboardPage.jsx       # Camera grid, status, controls
    │   ├── SettingsPage.jsx        # Node + group + recording + danger zone
    │   ├── McpPage.jsx             # MCP keys + scope picker + agent activity + incident list
    │   ├── AdminPage.jsx           # Stream logs, MCP activity, audit trail
    │   ├── PricingPage.jsx         # Public pricing
    │   ├── SentinelPage.jsx        # Public marketing for the Sentinel AI
    │   ├── LegalPage.jsx           # Terms, privacy, etc. (`/legal/:page`)
    │   ├── DocsPage.jsx            # In-app documentation (owns `/docs`)
    │   ├── SignInPage.jsx / SignUpPage.jsx
    │   └── TestHlsPage.jsx         # Admin-only HLS debug page
    ├── components/                 # HlsPlayer, CameraCard, IncidentReportModal,
    │                               # NotificationBell, KeyRotationModal, AddNodeModal,
    │                               # UpgradeModal, ToastContainer, Layout,
    │                               # HeartbeatBanner (first-heartbeat polling after
    │                               #   node creation, localStorage-backed),
    │                               # WelcomeHero (Admin / Member empty-state heroes),
    │                               # CameraGridPreview, DocsDiagrams, EmptyState,
    │                               # PublicLayout, LandingNav, LandingFooter,
    │                               # LoadingSpinner
    ├── hooks/                      # useNotifications, useMotionAlerts, usePlanInfo,
    │                               # useSharedToken, useToasts
    └── services/api.js             # Typed client for every backend endpoint
```

---

## Development

### Backend

```bash
cd backend
uv sync
uv run python start.py          # :8000 with auto-reload
uv run pytest                   # Runs the test suite
```

### Frontend

```bash
cd frontend
npm install
npm run dev                      # :5173
npm run build                    # Production build → backend/static/
```

### Database

SQLite for development (`opensentry.db` in backend directory). Tables auto-create on startup. For production, set `DATABASE_URL` to a PostgreSQL connection string.

---

## Deployment

Deployed on [Fly.io](https://fly.io) via GitHub Actions:

1. Frontend is built and copied to `backend/static/` by CI
2. FastAPI serves the React bundle; SPA middleware routes non-API requests to `index.html`
3. Live video segments are cached in the backend's process memory — no external storage
4. Clerk handles authentication (no user database needed)

Memory sizing: each camera uses ~7.5 MB of cache (`SEGMENT_CACHE_MAX_PER_CAMERA × ~125 KB per 1-second segment`). The default 1 GB Fly instance comfortably handles ~130 cameras with headroom. Bump `[[vm]] memory_mb` if you need more.

Production URL: [opensentry-command.fly.dev](https://opensentry-command.fly.dev)

---

## Troubleshooting

### Live video never shows up in the dashboard

Symptom: the camera appears in the grid but the tile stays black, or the HLS player loops the buffering spinner.

Check, in order:

1. **CloudNode heartbeat is arriving.** Visit `/settings`, find the node, confirm "Last seen" updates every ~30s. If it doesn't, the node never registered — check CloudNode logs for a `register` failure.
2. **Segments are being pushed.** In the browser devtools Network tab, look for `GET /api/cameras/{id}/segment/...` returning `200`. If they 404, the CloudNode isn't pushing — check `POST /api/cameras/{id}/push-segment` on the CloudNode side.
3. **The playlist is fresh.** `GET /api/cameras/{id}/stream.m3u8` — if the `#EXTINF` segment list is empty or the `segment/...` URLs are stale, the CloudNode's playlist upload stalled.
4. **The browser can decode the codec.** Admin-only `/test-hls` (the `TestHlsPage`) shows the raw SPS-derived codec string. If it's missing, the CloudNode's libx264 / hardware encoder wrote a non-conforming SPS — update the CloudNode to ≥ v0.1.15 and restart it.

The companion runbook in the CloudNode repo (`docs/runbooks/video-not-showing.md`) walks through this from the node's side.

### "Your plan doesn't allow another node"

You're at the plan's node limit. `GET /api/nodes/plan` returns `{ nodes_used, nodes_limit }`. Upgrade from the Pricing page or delete an unused node from Settings.

### Motion events don't appear

- Motion reporting is controlled by the CloudNode's `motion.enabled` config — if it's off, no events will ever arrive.
- The dashboard subscribes to `/api/motion/events/stream` (SSE). If your deployment is behind a proxy that buffers responses, SSE may never flush — make sure proxy-buffering is disabled for `/api/*/stream`.
- Per-org rate limits cap motion events at 120/min per camera; check `app/api/motion.py` if you need to tune this.

### MCP tools don't show up in my agent

- Make sure the agent is on Pro or Business — MCP access is plan-gated at the organization layer (see `app.core.auth` / `get_mcp_plan_info`).
- The installer scripts only patch configs for clients that already exist on the machine. If you installed Cursor *after* running `mcp-setup.sh`, re-run the installer.
- `GET /api/mcp/activity/stream` is the fastest way to confirm the agent is hitting your backend at all — if you see calls but `403`s, the key's `scope_mode` doesn't cover the tool the agent invoked.

---

## License

[AGPL-3.0](LICENSE) — source-available. You may self-host and modify the code, but if you offer a modified version to users over a network, AGPL §13 requires you to make your changes available to those users.

This project is **not currently accepting external code contributions**. Bug reports and feature requests via [Issues](https://github.com/SourceBox-LLC/OpenSentry-Command/issues) and [Discussions](https://github.com/SourceBox-LLC/OpenSentry-Command/discussions) are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

---

<p align="center">
  <a href="https://opensentry-command.fly.dev">OpenSentry Command Center</a>
  &middot;
  <a href="https://github.com/SourceBox-LLC/OpenSentry-CloudNode">CloudNode</a>
  &middot;
  Made by <a href="https://github.com/SourceBox-LLC">SourceBox LLC</a>
</p>
