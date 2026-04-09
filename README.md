# OpenSentry Command Center

**Cloud-hosted security camera management with real-time HLS streaming.**

Built with **FastAPI + React + Clerk Authentication + Tigris Storage**

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  CloudNode      │────▶│  Tigris/S3      │◀────│  Command Center │
│  (Rust)         │     │  (Video Storage) │     │  (FastAPI)       │
│  USB Camera     │     │                  │     │  + React         │
│  Codec Detect   │     │  - HLS Segments  │     │  + Clerk Auth    │
│  Segment Upload │     │  - M3U8 Playlist │     │                  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                                                │
        │ POST /upload-url                              │ GET /stream.m3u8
        │ POST /upload-complete                         │ GET /segment/{id}
        │ POST /playlist                                │
        │ POST /register (codec info)                   │
        └────────────────────────────────────────────────┘
```

**Key Components:**
- **CloudNode** (Rust) - Captures USB camera, detects codec, uploads HLS segments to Tigris
- **Command Center** (FastAPI) - Serves HLS manifests with codec info, handles authentication
- **MCP Server** - AI tool interface allowing MCP clients (Claude Code, etc.) to view cameras, check status, and query logs
- **Tigris/S3** - Object storage for video segments and playlists
- **Clerk** - Multi-tenant authentication with organization-based access

---

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- uv (Python package manager)
- Tigris/S3 bucket for video storage

### Backend Setup

```bash
cd backend

# Copy environment file
cp .env.example .env

# Edit .env with your settings
# Required: CLERK_SECRET_KEY, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
# Required: AWS_ENDPOINT_URL_S3 (Tigris endpoint)
# Required: TIGRIS_BUCKET_NAME

# Install dependencies
uv sync

# Run development server
uv run fastapi dev app/main.py
```

### Frontend Setup

```bash
cd frontend

# Copy environment file
cp .env.example .env

# Edit .env
# Set VITE_API_URL=http://localhost:8000
# Set VITE_CLERK_PUBLISHABLE_KEY (from Clerk dashboard)

# Install dependencies
npm install

# Run development server
npm run dev
```

The app will be available at `http://localhost:5173`

---

## Environment Variables

### Backend (`.env`)

```env
# Clerk Authentication
CLERK_SECRET_KEY=sk_test_xxx
CLERK_PUBLISHABLE_KEY=pk_test_xxx
CLERK_JWKS_URL=https://xxx.clerk.accounts.dev/.well-known/jwks.json

# Tigris/S3 Storage
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
AWS_ENDPOINT_URL_S3=https://fly.storage.tigris.dev
AWS_REGION=auto
TIGRIS_BUCKET_NAME=opensentry-storage

# Database
DATABASE_URL=sqlite:///./opensentry.db

# Frontend URL (for CORS)
FRONTEND_URL=http://localhost:5173

# Upload/Stream URL Expiry
UPLOAD_URL_EXPIRY_SECONDS=3600
STREAM_URL_EXPIRY_SECONDS=300

# Segment Cleanup
SEGMENT_RETENTION_COUNT=60
CLEANUP_INTERVAL=20
```

### Frontend (`.env`)

```env
VITE_API_URL=http://localhost:8000
VITE_CLERK_PUBLISHABLE_KEY=pk_test_xxx
```

---

## Project Structure

```
backend/
├── app/
│   ├── api/
│   │   ├── cameras.py        # Camera CRUD, settings, alerts
│   │   ├── hls.py            # HLS playlist/segment serving
│   │   ├── nodes.py          # CloudNode registration, heartbeat
│   │   ├── streams.py        # Upload URL generation, cleanup
│   │   ├── audit.py          # Stream access logs
│   │   ├── mcp_activity.py   # MCP activity SSE + REST + DB logs
│   │   └── webhooks.py       # Clerk webhooks
│   ├── core/
│   │   ├── auth.py           # Clerk JWT verification, permissions
│   │   ├── config.py         # Settings from environment
│   │   ├── database.py       # SQLAlchemy setup
│   │   └── clerk.py          # Clerk client
│   ├── mcp/
│   │   ├── server.py         # MCP tool definitions (FastMCP)
│   │   └── activity.py       # In-memory tracker + DB persistence
│   ├── models/
│   │   └── models.py         # SQLAlchemy models
│   ├── schemas/
│   │   └── schemas.py        # Pydantic request/response schemas
│   ├── services/
│   │   └── storage.py        # Tigris/S3 operations
│   └── main.py               # FastAPI app entry + MCP mount
├── .env.example
└── pyproject.toml

frontend/
├── src/
│   ├── components/
│   │   ├── HlsPlayer.jsx     # HLS.js video player
│   │   ├── CameraCard.jsx    # Camera feed display
│   │   ├── AddNodeModal.jsx  # Node creation
│   │   └── ...
│   ├── pages/
│   │   ├── DashboardPage.jsx # Camera grid view
│   │   ├── SettingsPage.jsx  # Node management
│   │   ├── AdminPage.jsx     # Stream logs + MCP activity
│   │   ├── McpPage.jsx       # MCP Control Center (live monitoring)
│   │   └── ...
│   ├── services/
│   │   └── api.js            # API client
│   └── App.jsx               # Routes and auth
├── .env.example
└── package.json
```

---

## API Endpoints

### Authentication Required (Clerk JWT)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/cameras` | List cameras |
| GET | `/api/cameras/{id}` | Get camera details |
| GET | `/api/camera-groups` | List camera groups |
| POST | `/api/camera-groups` | Create group |
| DELETE | `/api/camera-groups/{id}` | Delete group |
| PUT | `/api/cameras/{id}/group` | Assign camera to group |
| GET | `/api/settings` | Get all settings |
| POST | `/api/settings/recording` | Update recording settings |
| GET | `/api/nodes` | List nodes |
| POST | `/api/nodes` | Create node |
| GET | `/api/nodes/{id}` | Get node details |
| DELETE | `/api/nodes/{id}` | Delete node |
| POST | `/api/nodes/{id}/rotate-key` | Regenerate API key |

### Node Authentication (API Key)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/nodes/register` | Register CloudNode |
| POST | `/api/nodes/heartbeat` | Node heartbeat |
| POST | `/api/nodes/validate` | Validate credentials |
| POST | `/api/cameras/{id}/upload-url` | Get presigned upload URL |
| POST | `/api/cameras/{id}/upload-complete` | Confirm segment upload |
| POST | `/api/cameras/{id}/playlist` | Update HLS playlist |
| POST | `/api/cameras/{id}/codec` | Report detected codec |

### HLS Streaming (Clerk JWT)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/cameras/{id}/stream.m3u8` | Get HLS playlist |
| GET | `/api/cameras/{id}/segment/{filename}` | Get HLS segment |

### MCP (Model Context Protocol)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/mcp/` | MCP JSON-RPC endpoint (Bearer token auth) |
| GET | `/mcp/` | MCP Control Center dashboard |

### MCP Activity (Clerk JWT, Admin)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/mcp/activity/stream` | SSE stream of live MCP tool calls |
| GET | `/api/mcp/activity/recent` | Recent in-memory events |
| GET | `/api/mcp/activity/sessions` | Active MCP client sessions |
| GET | `/api/mcp/activity/stats` | Real-time aggregate stats |
| GET | `/api/mcp/activity/logs` | Persisted MCP logs (DB-backed) |
| GET | `/api/mcp/activity/logs/stats` | Historical MCP statistics |

---

## MCP Integration

The Command Center doubles as an MCP server, allowing AI clients (Claude Code, Cursor, etc.) to interact with cameras and system data via the [Model Context Protocol](https://modelcontextprotocol.io/).

### Available Tools (Read-Only)

| Tool | Description |
|------|-------------|
| `view_camera` | Live JPEG snapshot from a camera |
| `watch_camera` | Multiple snapshots over time (2-10 frames) |
| `list_cameras` | List all cameras with status |
| `get_camera` | Camera details by ID |
| `get_stream_url` | Pre-signed HLS stream URL |
| `list_nodes` | List all camera nodes |
| `get_node` | Node details by ID |
| `list_camera_groups` | List camera groups |
| `get_recording_settings` | Current recording configuration |
| `get_stream_logs` | Stream access history |
| `get_stream_stats` | Aggregated stream statistics |
| `get_system_status` | System overview (cameras, nodes, plan) |

### Connecting Claude Code

```bash
claude mcp add opensentry \
  --transport http \
  --url https://your-domain.fly.dev/mcp/ \
  --header "Authorization: Bearer YOUR_MCP_API_KEY" \
  --scope user
```

Generate an API key from the MCP Control Center page in the web dashboard.

### Rate Limits

MCP tool calls are rate limited per API key based on the organization's plan:

| Plan | Calls/min |
|------|-----------|
| Pro | 30 |
| Business | 120 |

Exceeding the limit returns an error until the sliding window resets.

### Architecture

- MCP server built with [FastMCP](https://github.com/jlowin/fastmcp), mounted at `/mcp/` inside the FastAPI app
- Stateless HTTP transport — each request is an independent JSON-RPC call
- Auth via Bearer token using org-scoped MCP API keys (SHA-256 hashed)
- Per-key sliding-window rate limiting based on org plan
- All tool calls are logged to the database and streamed via SSE to the MCP Control Center
- Visual tools (`view_camera`, `watch_camera`) send WebSocket commands to the CloudNode to capture live JPEG snapshots
- Automatic log retention: logs older than 90 days are cleaned up daily (configurable via `LOG_RETENTION_DAYS`)

---

## CloudNode Integration

The Rust CloudNode sends:

1. **Registration** (`POST /api/nodes/register`)
   - Node ID, API key, camera list
   - Detected video/audio codecs

2. **Heartbeat** (`POST /api/nodes/heartbeat`)
   - Camera status updates

3. **Segment Upload**
   - Request presigned URL (`POST /api/cameras/{id}/upload-url`)
   - Upload to Tigris
   - Confirm upload (`POST /api/cameras/{id}/upload-complete`)
   - Update playlist (`POST /api/cameras/{id}/playlist`)

---

## Codec Detection

CloudNode detects codecs during setup and stores them in the database:

```rust
// CloudNode setup
let codec_info = detect_codec_from_camera(&camera_device)?;
// Returns: { video_codec: "avc1.42e01e", audio_codec: "mp4a.40.2" }

// Sent during registration
POST /api/nodes/register
{
  "node_id": "...",
  "cameras": [...],
  "video_codec": "avc1.42e01e",
  "audio_codec": "mp4a.40.2"
}
```

Backend uses stored codecs in HLS manifest:
```python
# hls.py
video_codec = node.video_codec or "avc1.42e01e"
audio_codec = node.audio_codec or "mp4a.40.2"
playlist_text = re.sub(
    r"(#EXT-X-VERSION:\d+)",
    rf"\1\n#EXT-X-CODECS:{video_codec},{audio_codec}",
    playlist_text,
)
```

---

## Permissions

Clerk V2 JWT format:

```python
# Required permissions:
org:admin:admin           # Full admin access
org:cameras:manage_cameras # Create/delete nodes
org:cameras:view_cameras  # View camera feeds
```

---

## Deployment

### Fly.io

```bash
# Install flyctl
flyctl deploy
```

Environment variables set in `fly.toml` or via `flyctl secrets set`

### Docker

```bash
docker build -t opensentry-command .
docker run -p 8000:8000 --env-file .env opensentry-command
```

---

## Development

```bash
# Backend - FastAPI with auto-reload
cd backend
uv run fastapi dev app/main.py

# Frontend - Vite with hot reload
cd frontend
npm run dev

# Run tests (if present)
cd backend
uv run pytest
```

---

## Cleaned Up

- Removed legacy Flask codebase (`opensentry_command/`)
- Removed outdated Docker files
- Removed unused Pygame/RTSP code
- Consolidated to FastAPI + React architecture

---

## License

GNU General Public License v3.0 - See [LICENSE](LICENSE)

---

**Built with FastAPI, React, Clerk, and Tigris Object Storage**