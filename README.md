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
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Backend-FastAPI_2.0-009688.svg" alt="FastAPI"></a>
  <a href="https://react.dev/"><img src="https://img.shields.io/badge/Frontend-React_19-61DAFB.svg" alt="React"></a>
</p>

---

OpenSentry Command Center is the cloud hub for the OpenSentry ecosystem. It receives live HLS video streams from [CloudNode](https://github.com/SourceBox-LLC/OpenSentry-CloudNode) devices on your local network, caches segments in memory, and serves them to any browser same-origin. Authentication and multi-tenant isolation are handled by Clerk.

**What it does:**
- Receives live HLS video pushed directly from CloudNode devices
- Caches the most recent segments per camera in RAM and serves them through the authenticated backend
- Manages camera nodes, groups, alerts, and media
- Multi-tenant with organization-based access control
- Audit logging for all stream access

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
  │ FFmpeg (HLS) │──push────→ │  In-memory segment     │──GET──→ │  HLS.js      │
  │              │  segments  │  cache (~15 segs/cam)  │  +JWT   │  (video)     │
  │              │──register─→│  SQLite / PostgreSQL   │         │              │
  │              │──heartbeat→│  Clerk Auth            │←─JWT───→│  Clerk Auth  │
  └──────────────┘            └───────────────────────┘         └──────────────┘
```

**Video pipeline:** CloudNode transcodes USB camera video into HLS segments and `POST`s each `.ts` file directly to the Command Center, which holds the most recent segments per camera in an in-memory cache. The browser fetches the playlist from the backend (which rewrites segment paths to its own same-origin segment proxy), then downloads each segment from RAM with the user's JWT.

**Authentication:** Clerk handles user sign-up, login, and organization management. The backend validates JWT tokens and extracts organization-scoped permissions. CloudNodes authenticate with API keys (SHA-256 hashed in the database).

**Storage:** Live video segments live only in RAM. Recordings and snapshots stay on the local CloudNode. SQLite (dev) or PostgreSQL (production) holds application data. Old segments are evicted automatically as new ones arrive.

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
| `SEGMENT_PUSH_MAX_BYTES` | No | `2097152` | Max bytes per pushed `.ts` segment |
| `CLEANUP_INTERVAL` | No | `20` | Cache eviction sweep every N playlist updates |
| `INACTIVE_CAMERA_CLEANUP_HOURS` | No | `24` | Free caches for cameras offline this long |
| `AUDIT_LOG_RETENTION_DAYS` | No | `7` | Stream access log retention |
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
| POST | `/api/cameras/{camera_id}/codec` | Node | Report video/audio codec |

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
| POST | `/api/nodes` | Admin | Create a node |
| GET | `/api/nodes/{node_id}` | Admin | Get node details |
| DELETE | `/api/nodes/{node_id}` | Admin | Delete node |
| POST | `/api/nodes/{node_id}/rotate-key` | Admin | Rotate API key |
| POST | `/api/nodes/register` | Node | CloudNode registration |
| POST | `/api/nodes/heartbeat` | Node | CloudNode heartbeat |

### HLS Streaming

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/cameras/{camera_id}/stream.m3u8` | User | Cached HLS playlist with same-origin segment URLs |
| GET | `/api/cameras/{camera_id}/segment/{file}` | User | Serve a single cached `.ts` segment from memory |
| POST | `/api/cameras/{camera_id}/push-segment?filename=…` | Node | Push a `.ts` segment into the in-memory cache |
| POST | `/api/cameras/{camera_id}/playlist` | Node | Update the cached HLS playlist |
| POST | `/api/cameras/{camera_id}/codec` | Node | Report video/audio codec |

### Settings & Media

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/settings` | User | All settings |
| GET/POST | `/api/settings/notifications` | User | Notification settings |
| GET/POST | `/api/settings/recording` | User | Recording settings |
| GET | `/api/media` | User | List media |
| GET | `/api/media/{media_id}` | User | Get media |
| DELETE | `/api/media/{media_id}` | Admin | Delete media |

### Alerts & Audit

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/api/alerts` | User | List alerts |
| GET | `/api/alerts/{alert_id}` | User | Get alert |
| DELETE | `/api/alerts/{alert_id}` | Admin | Delete alert |
| GET | `/api/audit-logs` | Admin | List audit logs |
| GET | `/api/audit/stream-logs` | Admin | Stream access logs |
| GET | `/api/audit/stream-logs/stats` | Admin | Stream access stats |

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
│   │   ├── cameras.py       # Camera, group, settings, alert, media endpoints
│   │   ├── nodes.py         # CloudNode registration, heartbeat, CRUD
│   │   ├── hls.py           # HLS playlist + in-memory segment cache + push-segment
│   │   ├── audit.py         # Stream access logging
│   │   └── webhooks.py      # Clerk subscription webhooks
│   ├── core/
│   │   ├── auth.py          # Clerk JWT validation, permission enforcement
│   │   ├── config.py        # Environment variable loading
│   │   ├── clerk.py         # Clerk SDK initialization
│   │   └── database.py      # SQLAlchemy engine and session
│   ├── models/
│   │   └── models.py        # Camera, CameraNode, CameraGroup, Media,
│   │                        # Alert, Setting, AuditLog, StreamAccessLog
│   └── schemas/
│       └── schemas.py       # Pydantic request/response schemas
├── .env.example
├── pyproject.toml
└── start.py                 # Uvicorn entry point

frontend/
└── src/
    ├── pages/
    │   └── DashboardPage.jsx    # Camera grid, status, controls
    └── components/
        └── HlsPlayer.jsx       # HLS.js video player
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
3. Live HLS segments are held in process memory — size the Fly machine RAM for ~4 MB per active camera (default 1 GB instance fits ~100 cameras with headroom)
4. Clerk handles authentication (no user database needed)

Production URL: [opensentry-command.fly.dev](https://opensentry-command.fly.dev)

---

## License

MIT -- Free for personal and commercial use.

---

<p align="center">
  <a href="https://opensentry-command.fly.dev">OpenSentry Command Center</a>
  &middot;
  <a href="https://github.com/SourceBox-LLC/OpenSentry-CloudNode">CloudNode</a>
  &middot;
  Made by <a href="https://github.com/SourceBox-LLC">SourceBox LLC</a>
</p>
