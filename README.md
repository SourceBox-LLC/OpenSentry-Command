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
- Receives live HLS video from CloudNode devices and proxies it to the browser
- Caches segments in memory (~3.75 MB per camera) — no S3, no presigned URLs
- Manages camera nodes and groups, with per-org Clerk authentication
- Multi-tenant with organization-based access control
- Audit logging for all stream access and MCP tool calls
- MCP server exposing 22 tools so AI clients can view cameras, file incident reports with snapshots and short video clips, and read back past investigations

---

## Quick Start

### Prerequisites

- **Python** 3.10+
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

Create a camera node from the Settings page, then run [CloudNode](https://github.com/SourceBox-LLC/OpenSentry-CloudNode) with those credentials:

```bash
opensentry-cloudnode setup
# Enter your Node ID, API Key, and Command Center URL
```

Cameras auto-register when the CloudNode connects.

---

## Architecture

```
   CloudNode (Rust)                  Command Center                    Browser
  ┌──────────────┐            ┌───────────────────────┐         ┌──────────────┐
  │ USB Camera   │            │  FastAPI Backend       │         │  React 19    │
  │      ↓       │            │                        │         │              │
  │ FFmpeg (HLS) │──push─────→│  In-memory segment     │←─GET──→ │  HLS.js      │
  │              │  segments  │  cache (~15 segs/cam)  │ proxy   │  (video)     │
  │              │──register─→│  SQLite / PostgreSQL   │  URLs   │              │
  │              │──heartbeat→│  Clerk Auth            │←─JWT───→│  Clerk Auth  │
  └──────────────┘            └───────────────────────┘         └──────────────┘
```

**Video pipeline:** CloudNode transcodes USB camera video into HLS segments and pushes each `.ts` file directly to the backend via `POST /api/cameras/{id}/push-segment`. The backend caches segments in memory (15 per camera by default) and serves them through the same-origin proxy at `GET /api/cameras/{id}/segment/{file}`. The browser fetches the rewritten playlist and downloads segments through the backend — no S3, no presigned URLs.

**Authentication:** Clerk handles user sign-up, login, and organization management. The backend validates JWT tokens and extracts organization-scoped permissions. CloudNodes authenticate with API keys (SHA-256 hashed in the database).

**Storage:** Live segments live in the backend's in-memory cache. SQLite (dev) or PostgreSQL (production) for application data. Recordings and snapshots are stored locally on each CloudNode. Old segments fall out of the cache automatically based on `SEGMENT_CACHE_MAX_PER_CAMERA`.

---

## Configuration

### Backend environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CLERK_SECRET_KEY` | Yes | | Clerk backend API key |
| `CLERK_PUBLISHABLE_KEY` | Yes | | Clerk frontend key |
| `CLERK_JWKS_URL` | No | | JWT validation endpoint |
| `CLERK_WEBHOOK_SECRET` | No | | Webhook signature verification |
| `DATABASE_URL` | No | `sqlite:///./opensentry.db` | Database connection string |
| `FRONTEND_URL` | No | `http://localhost:5173` | CORS origin |
| `SEGMENT_CACHE_MAX_PER_CAMERA` | No | `15` | Segments cached in memory per camera |
| `SEGMENT_PUSH_MAX_BYTES` | No | `2097152` | Max bytes per pushed segment (2 MB) |
| `CLEANUP_INTERVAL` | No | `20` | Run cache eviction every N playlist updates |
| `INACTIVE_CAMERA_CLEANUP_HOURS` | No | `24` | Free caches for cameras offline this long |
| `LOG_RETENTION_DAYS` | No | `90` | Stream, MCP, and audit log retention |
| `SESSION_TIMEOUT` | No | `30` | Session timeout (minutes) |

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
| POST | `/api/cameras/{camera_id}/codec` | Node | Report video/audio codec (called by CloudNode) |

### Camera Groups

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/camera-groups` | User | List groups |
| POST | `/api/camera-groups` | Admin | Create group |
| DELETE | `/api/camera-groups/{group_id}` | Admin | Delete group |
| PUT | `/api/cameras/{camera_id}/group` | Admin | Assign camera to group |

### Camera Nodes

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/nodes` | Admin | List all nodes |
| POST | `/api/nodes` | Admin | Create a node (requires active billing) |
| GET | `/api/nodes/{node_id}` | Admin | Get node details |
| DELETE | `/api/nodes/{node_id}` | Admin | Delete node |
| POST | `/api/nodes/{node_id}/rotate-key` | Admin | Rotate API key |
| GET | `/api/nodes/plan` | User | Current plan, usage, and limits |
| GET | `/api/nodes/ws-status` | Admin | Which org nodes are WebSocket-connected |
| POST | `/api/nodes/validate` | Node | Validate a node_id + API key pair (used by CloudNode setup wizard) |
| POST | `/api/nodes/register` | Node | CloudNode registration |
| POST | `/api/nodes/heartbeat` | Node | CloudNode heartbeat |

### HLS Streaming

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/cameras/{camera_id}/stream.m3u8` | User | HLS playlist (cached, with relative segment URLs) |
| GET | `/api/cameras/{camera_id}/segment/{file}` | User | Serve cached segment from memory |
| POST | `/api/cameras/{camera_id}/push-segment` | Node | Push a `.ts` segment into the in-memory cache |
| POST | `/api/cameras/{camera_id}/playlist` | Node | Update playlist |
| POST | `/api/cameras/{camera_id}/codec` | Node | Report video/audio codec |

### Settings

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/settings` | User | All settings |
| GET | `/api/settings/recording` | User | Recording settings |
| POST | `/api/settings/recording` | Admin | Update recording settings |
| POST | `/api/settings/danger/wipe-logs` | Admin | Permanently delete all stream + MCP logs (Pro/Business only) |
| POST | `/api/settings/danger/full-reset` | Admin | Wipe all nodes, cameras, logs, and settings for the org (Pro/Business only) |

### Audit

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/audit-logs` | Admin | List audit logs |
| GET | `/api/audit/stream-logs` | Admin | Stream access logs |
| GET | `/api/audit/stream-logs/stats` | Admin | Stream access stats |

### Incident Reports

AI-generated incident reports. Agents write them via the MCP tools below; admins review them from the dashboard Incidents tab.

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/incidents` | Admin | List incidents (filter by `status`, `severity`, `camera_id`) |
| GET | `/api/incidents/counts` | Admin | Aggregate counts (open, open critical, open high, total) |
| GET | `/api/incidents/{incident_id}` | Admin | Get incident detail + all evidence metadata |
| PATCH | `/api/incidents/{incident_id}` | Admin | Acknowledge / resolve / dismiss / edit an incident |
| DELETE | `/api/incidents/{incident_id}` | Admin | Delete an incident (cascades to evidence) |
| GET | `/api/incidents/{incident_id}/evidence/{evidence_id}` | Admin | Stream a snapshot or clip blob attached as evidence |
| GET | `/api/incidents/{incident_id}/evidence/{evidence_id}/playlist.m3u8` | Admin | Synthetic single-segment HLS playlist for clip playback in the dashboard |

### MCP (for AI clients)

Streamable HTTP MCP server exposing 22 tools. See [AGENTS.md](AGENTS.md) for the full tool list. Requires a Pro or Business plan + an MCP API key generated from the dashboard.

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/mcp` | MCP Key | Streamable HTTP MCP endpoint (`Authorization: Bearer osc_...`) |
| GET | `/api/mcp/keys` | Admin | List MCP API keys |
| POST | `/api/mcp/keys` | Admin | Generate a new MCP API key (shown once, requires active billing) |
| DELETE | `/api/mcp/keys/{key_id}` | Admin | Revoke a key |
| GET | `/api/mcp/activity/stream` | Admin | Server-Sent Events stream of live MCP calls |
| GET | `/api/mcp/activity/recent` | Admin | Recent MCP tool calls |
| GET | `/api/mcp/activity/sessions` | Admin | MCP session summaries |
| GET | `/api/mcp/activity/stats` | Admin | Aggregated stats by tool / key / time |
| GET | `/api/mcp/activity/logs` | Admin | MCP tool call activity log (filterable) |
| GET | `/api/mcp/activity/logs/stats` | Admin | Summary counts for MCP logs |

### System

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/health` | None | Health check |
| POST | `/api/webhooks/clerk` | Webhook | Clerk subscription events |

**Auth types:** `User` = Clerk JWT, `Admin` = Clerk JWT with admin permission, `Node` = `X-Node-API-Key` header.

---

## Permissions

Access control uses Clerk organizations with V2 JWT permissions:

| Permission | Grants |
|------------|--------|
| `org:admin:admin` | Full access (nodes, groups, media, audit logs) |
| `org:cameras:manage_cameras` | Manage cameras and nodes |
| `org:cameras:view_cameras` | View cameras and live feeds |

Admin permission is required for node management, group management, media deletion, and audit log access. View permission is sufficient for watching streams and viewing camera status.

---

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app, CORS, SPA middleware, cleanup loop
│   ├── api/
│   │   ├── cameras.py       # Camera, group, settings, audit log, danger-zone endpoints
│   │   ├── nodes.py         # CloudNode registration, heartbeat, CRUD, plan info
│   │   ├── hls.py           # HLS playlist + in-memory segment cache + push-segment
│   │   ├── audit.py         # Stream access logging
│   │   ├── incidents.py     # AI-generated incident reports (CRUD + evidence blobs)
│   │   ├── mcp_keys.py      # MCP API key management
│   │   ├── mcp_activity.py  # MCP tool call activity logs + stats + SSE stream
│   │   ├── install.py       # Signed CloudNode installer endpoints
│   │   ├── ws.py            # WebSocket helpers
│   │   └── webhooks.py      # Clerk subscription webhooks
│   ├── mcp/
│   │   └── server.py        # FastMCP server + all 22 MCP tools
│   ├── core/
│   │   ├── auth.py          # Clerk JWT validation, permission enforcement
│   │   ├── config.py        # Environment variable loading
│   │   ├── clerk.py         # Clerk SDK initialization
│   │   └── database.py      # SQLAlchemy engine and session
│   ├── models/
│   │   └── models.py        # Camera, CameraNode, CameraGroup,
│   │                        # Setting, AuditLog, StreamAccessLog,
│   │                        # Incident, IncidentEvidence, McpApiKey, McpToolCall
│   └── schemas/
│       └── schemas.py       # Pydantic request/response schemas
├── .env.example
├── pyproject.toml
└── start.py                 # Uvicorn entry point

frontend/
└── src/
    ├── pages/
    │   ├── DashboardPage.jsx       # Camera grid, status, controls
    │   ├── McpPage.jsx             # MCP keys, agent activity, incident list
    │   ├── AdminPage.jsx           # Stream logs, MCP activity, audit trail
    │   └── DocsPage.jsx            # In-app documentation
    └── components/
        ├── HlsPlayer.jsx           # HLS.js video player
        └── IncidentReportModal.jsx # Incident detail view with markdown + evidence
```

---

## Development

### Backend

```bash
cd backend
uv sync
uv run python start.py          # Runs on :8000 with auto-reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev                      # Runs on :5173
npm run build                    # Production build → backend/static/
```

### Database

SQLite for development (`opensentry.db` in backend directory). Tables are created automatically on startup. For production, set `DATABASE_URL` to a PostgreSQL connection string.

---

## Deployment

The app is deployed on [Fly.io](https://fly.io):

1. Frontend is built and served as static files by the FastAPI backend
2. SPA middleware routes non-API requests to `index.html`
3. Live video segments are cached in the backend's process memory — no external storage
4. Clerk handles authentication (no user database needed)

Memory sizing: each camera uses ~3.75 MB of cache (`SEGMENT_CACHE_MAX_PER_CAMERA × ~250 KB`). The default Fly instance is 1 GB, which comfortably handles ~150 cameras with headroom. Bump `[[vm]] memory_mb` if you need more.

Production URL: [opensentry-command.fly.dev](https://opensentry-command.fly.dev)

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
