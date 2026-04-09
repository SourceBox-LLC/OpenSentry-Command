# OpenSentry Command - Agent Documentation

## Project Overview

OpenSentry is a cloud-hosted multi-tenant security camera system with two main components:

1. **OpenSentry Command Center** (FastAPI + React) - Cloud-hosted application with Clerk authentication
2. **OpenSentry CloudNode** (Rust) - Local application that captures USB camera video and streams to the cloud

**Project Locations:**
- Command Center: `C:\Users\Sbuss\Documents\Software Development\Projects\OpenSentry Command`
- CloudNode: `C:\Users\Sbuss\Documents\Software Development\Projects\OpenSentry-CloudNode`

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
```

**Video Flow:**
1. CloudNode captures USB camera video
2. CloudNode detects codecs during setup (H.264 Baseline/Main, AAC)
3. CloudNode uploads HLS segments to Tigris via presigned URLs
4. CloudNode updates M3U8 playlist in Tigris
5. Browser requests M3U8 from Command Center
6. Command Center serves M3U8 with stored codec info
7. Browser plays HLS stream via HLS.js

---

## Key Files

### Backend (Python)

| File | Purpose |
|------|---------|
| `backend/app/main.py` | FastAPI app entry point, MCP mount, SPA middleware |
| `backend/app/api/cameras.py` | Camera CRUD, settings, alerts, audit logs |
| `backend/app/api/nodes.py` | CloudNode registration, heartbeat, validation |
| `backend/app/api/hls.py` | HLS playlist/segment serving with codec injection |
| `backend/app/api/streams.py` | Upload URL generation, segment cleanup |
| `backend/app/api/mcp_activity.py` | MCP activity SSE streaming + DB-backed log endpoints |
| `backend/app/mcp/server.py` | MCP tool definitions (FastMCP) — read-only camera tools |
| `backend/app/mcp/activity.py` | In-memory activity tracker + DB persistence |
| `backend/app/core/auth.py` | Clerk JWT V2 verification, permission decoding |
| `backend/app/services/storage.py` | Tigris/S3 operations (upload, download, cleanup) |
| `backend/app/models/models.py` | SQLAlchemy models (CameraNode, Camera, McpActivityLog, etc.) |
| `backend/app/schemas/schemas.py` | Pydantic request/response schemas |

### Frontend (React)

| File | Purpose |
|------|---------|
| `frontend/src/App.jsx` | Routes and auth setup |
| `frontend/src/pages/DashboardPage.jsx` | Camera grid view |
| `frontend/src/pages/SettingsPage.jsx` | Node management |
| `frontend/src/pages/AdminPage.jsx` | Stream access logs + MCP activity audit |
| `frontend/src/pages/McpPage.jsx` | MCP Control Center (live monitoring, API keys, tools) |
| `frontend/src/components/HlsPlayer.jsx` | HLS.js video player |
| `frontend/src/components/CameraCard.jsx` | Camera feed card |
| `frontend/src/services/api.js` | API client with auth |

### CloudNode (Rust)

| File | Purpose |
|------|---------|
| `src/streaming/codec_detector.rs` | Codec detection from camera |
| `src/streaming/hls_uploader.rs` | Segment upload to Tigris |
| `src/api/client.rs` | HTTP client for Command Center API |
| `src/node/runner.rs` | Main node runner, registration |
| `src/setup/tui.rs` | Terminal UI setup wizard |
| `src/setup/validator.rs` | Credential validation |

---

## Database Schema

### CameraNode
```
node_id: String (unique)
name: String
org_id: String
api_key_hash: String (SHA256)
status: String (online/offline)
upload_count: Integer
video_codec: String (e.g., "avc1.42e01e")
audio_codec: String (e.g., "mp4a.40.2")
created_at: DateTime
```

### Camera
```
camera_id: String (unique)
name: String
node_id: Integer (FK to CameraNode)
org_id: String
status: String (online/offline/streaming)
video_codec: String
audio_codec: String
codec_detected_at: DateTime
last_seen: DateTime
```

### McpApiKey
```
id: Integer (PK)
org_id: String
key_hash: String (SHA-256, unique)
name: String
created_at: DateTime
last_used_at: DateTime (nullable)
revoked: Boolean
```

### McpActivityLog
```
id: Integer (PK)
org_id: String
tool_name: String
key_name: String
status: String (completed/error)
duration_ms: Integer
args_summary: String (nullable)
error: String (nullable)
timestamp: DateTime
```

---

## API Endpoints

### Authentication Required (Clerk JWT Bearer Token)

**Cameras:**
- `GET /api/cameras` - List all cameras
- `GET /api/cameras/{id}` - Get camera details
- `POST /api/cameras/{id}/group` - Assign camera to group

**Camera Groups:**
- `GET /api/camera-groups` - List groups
- `POST /api/camera-groups` - Create group
- `DELETE /api/camera-groups/{id}` - Delete group

**Settings:**
- `GET /api/settings` - Get all settings
- `POST /api/settings/recording` - Update recording settings
- `POST /api/settings/notifications` - Update notification settings

**Nodes:**
- `GET /api/nodes` - List all nodes
- `POST /api/nodes` - Create new node (returns API key)
- `GET /api/nodes/{id}` - Get node details
- `DELETE /api/nodes/{id}` - Delete node
- `POST /api/nodes/{id}/rotate-key` - Regenerate API key

**HLS Streaming:**
- `GET /api/cameras/{id}/stream.m3u8` - Get HLS playlist with auth
- `GET /api/cameras/{id}/segment/{filename}` - Get HLS segment with auth

**Admin:**
- `GET /api/audit-logs` - List audit logs (admin only)
- `GET /api/audit/stream-logs` - List stream access logs
- `GET /api/audit/stream-logs/stats` - Get stream statistics

**MCP Activity (Admin):**
- `GET /api/mcp/activity/stream` - SSE stream of live tool calls
- `GET /api/mcp/activity/recent` - Recent in-memory events
- `GET /api/mcp/activity/sessions` - Active MCP client sessions
- `GET /api/mcp/activity/stats` - Real-time aggregate stats
- `GET /api/mcp/activity/logs` - Persisted MCP logs (DB, filterable)
- `GET /api/mcp/activity/logs/stats` - Historical MCP stats (by tool, key, day)

### MCP Protocol (Bearer Token — MCP API Key)

- `POST /mcp/` - JSON-RPC endpoint for MCP tool calls

**Available Tools (read-only):**
- `view_camera` - Live JPEG snapshot from a camera
- `watch_camera` - Multiple snapshots over time
- `list_cameras` / `get_camera` - Camera info
- `get_stream_url` - Pre-signed HLS URL
- `list_nodes` / `get_node` - Node info
- `list_camera_groups` - Camera groups
- `get_recording_settings` - Recording config
- `get_stream_logs` / `get_stream_stats` - Access history
- `get_system_status` - System overview

### Node Authentication (X-API-Key Header)

- `POST /api/nodes/register` - Register CloudNode, send codecs
- `POST /api/nodes/heartbeat` - Node heartbeat, update status
- `POST /api/nodes/validate` - Validate credentials during setup
- `POST /api/cameras/{camera_id}/upload-url` - Get presigned upload URL
- `POST /api/cameras/{camera_id}/upload-complete` - Confirm segment uploaded
- `POST /api/cameras/{camera_id}/playlist` - Update M3U8 playlist
- `POST /api/cameras/{camera_id}/codec` - Report detected codec (also updates node codec if missing)

---

## Codec Detection Flow

### CloudNode Setup

```rust
// 1. Detect codec from camera during setup
let codec_info = detect_codec_from_camera(&device_path)?;
// Returns: CodecInfo { video_codec: "avc1.42e01e", audio_codec: "mp4a.40.2" }

// 2. Send during registration
POST /api/nodes/register
{
  "node_id": "abc123",
  "name": "Home",
  "cameras": [{ "device_path": "/dev/video0", ... }],
  "video_codec": "avc1.42e01e",
  "audio_codec": "mp4a.40.2"
}
```

### CloudNode Streaming

```rust
// 3. Detect codec from first successful segment upload (most accurate)
let codec_info = detect_codec(segment_path)?;
// POST /api/cameras/{camera_id}/codec
// Updates: camera.video_codec, camera.audio_codec
// Also updates: node.video_codec if node has no codec yet
```

### HLS Manifest Generation

```python
# Backend hls.py
# Priority: camera codec > node codec > default
video_codec = camera.video_codec or node.video_codec or "avc1.42e01e"
audio_codec = camera.audio_codec or node.audio_codec or "mp4a.40.2"

# Inject codecs into M3U8
playlist_text = re.sub(
    r"(#EXT-X-VERSION:\d+)",
    rf"\1\n#EXT-X-CODECS:{video_codec},{audio_codec}",
    playlist_text,
)
```

**Codec String Format (RFC 6381):**
- H.264 Baseline Level 3.0: `avc1.42e01e` (lowercase hex!)
- H.264 Baseline Level 3.1: `avc1.42e01f`
- H.264 Main Level 4.1: `avc1.4da029`
- AAC-LC: `mp4a.40.2`

---

## Segment Cleanup

Automatic cleanup runs every 20 uploads, keeps last 60 segments:

```python
# streams.py
if node.upload_count % settings.CLEANUP_INTERVAL == 0:
    storage.cleanup_old_segments(org_id, camera_id, keep_count=60)
```

---

## Clerk Authentication

### V2 JWT Format

```json
{
  "fea": "o:admin,o:cameras",
  "o": {
    "id": "org_123",
    "per": "admin,manage_cameras,view_cameras",
    "fpm": "1,3",
    "rol": "admin"
  }
}
```

### Permission Decoding

```python
def decode_v2_permissions(claims: dict) -> list:
    o_claim = claims.get("o", {})
    per_str = o_claim.get("per", "")
    permission_names = per_str.split(",") if per_str else []
    
    fea_claim = claims.get("fea", "")
    features = [f[2:] if f.startswith("o:") else f for f in fea_claim.split(",")]
    
    # Reconstruct: org:{feature}:{permission}
    permissions = []
    for i, feature in enumerate(features):
        for j, perm_name in enumerate(permission_names):
            if fpm_values[i] & (1 << j):
                permissions.append(f"org:{feature}:{perm_name}")
    
    return permissions
```

### Required Permissions

- `org:admin:admin` - Full admin access
- `org:cameras:manage_cameras` - Create/delete nodes, manage cameras
- `org:cameras:view_cameras` - View camera feeds

---

## MCP Server Architecture

The Command Center serves as an MCP (Model Context Protocol) server, allowing AI clients to interact with cameras.

### Key Design Decisions

- **FastMCP** with `stateless_http=True` and `json_response=True` — each POST is independent JSON-RPC
- **Mounted at `/mcp/`** inside FastAPI — SPA middleware routes GET to frontend, POST to MCP server
- **Auth via `get_http_headers(include={"authorization"})`** — FastMCP strips auth headers by default
- **Snapshot flow**: MCP server → WebSocket command to CloudNode → FFmpeg extracts JPEG from latest HLS segment → base64 back over WebSocket → returned as `Image` content
- **Response nesting**: CloudNode returns `{"status": "success", "data": {"image_b64": "..."}}` — tools extract via `result.get("data", {}).get("image_b64")`
- **Activity tracking**: Every tool call is logged in-memory (SSE to MCP dashboard) AND persisted to `mcp_activity_logs` table (background thread)
- **Read-only tools only** — no write operations exposed via MCP

### Connecting a Client

```bash
claude mcp add opensentry \
  --transport http \
  --url https://opensentry-command.fly.dev/mcp/ \
  --header "Authorization: Bearer YOUR_KEY" \
  --scope user
```

---

## Common Tasks

### Create a New Node

1. User clicks "Add Node" in Settings
2. Frontend calls `POST /api/nodes` with auth token
3. Backend generates `node_id` and `api_key`
4. Backend stores `api_key_hash` (SHA256), returns plain key once
5. User runs CloudNode with `--node-id` and `--api-key`
6. CloudNode validates credentials, detects codecs, registers

### Debug HLS Playback

1. Check backend logs: `[HLS] Using stored codec: avc1.42e01e,mp4a.40.2`
2. Check CloudNode logs: `[Codec] Detected from camera /dev/video0: video=avc1.42e01e`
3. Verify database: `select video_codec, audio_codec from camera_nodes;`
4. Check browser console: HLS.js will show `BufferCodecsChange` event

### Debug Registration

1. CloudNode sends: `POST /api/nodes/validate` to test credentials
2. If 404: "Node not found, create in Command Center first"
3. If 401: "Invalid API key, copy from Settings page"
4. If 200: Credentials valid, CloudNode continues setup

---

## Environment Variables

### Backend (.env)

```env
# Clerk
CLERK_SECRET_KEY=sk_test_xxx
CLERK_PUBLISHABLE_KEY=pk_test_xxx
CLERK_JWKS_URL=https://xxx.clerk.accounts.dev/.well-known/jwks.json

# Tigris/S3
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
AWS_ENDPOINT_URL_S3=https://fly.storage.tigris.dev
AWS_REGION=auto
TIGRIS_BUCKET_NAME=opensentry-storage

# Database
DATABASE_URL=sqlite:///./opensentry.db

# Frontend CORS
FRONTEND_URL=http://localhost:5173

# Storage Settings
UPLOAD_URL_EXPIRY_SECONDS=3600
STREAM_URL_EXPIRY_SECONDS=300
SEGMENT_RETENTION_COUNT=60
CLEANUP_INTERVAL=20
```

### Frontend (.env)

```env
VITE_API_URL=http://localhost:8000
VITE_CLERK_PUBLISHABLE_KEY=pk_test_xxx
```

---

## Deployment

### Fly.io

```bash
flyctl deploy
```

### Database Migrations

```bash
cd backend
uv run alembic revision --autogenerate -m "description"
uv run alembic upgrade head
```

---

## Recent Cleanup

Removed dead code:
- `backend/app/services/codec_prober.py` - Codec detection moved to CloudNode
- `storage.py`: `generate_segment_url()`, `verify_upload()`, `save_segment()` - Unused
- `schemas.py`: `CameraCreate`, `CameraUpdate`, `CameraResponse`, `MediaResponse`, `AlertResponse`, etc.
- `frontend/src/components/`: `StatusBadge.jsx`, `RecordingIndicator.jsx`, `DetectionBadge.jsx`
- `frontend/src/hooks/`: `useVideoFeed.js`, `useCameraControls.js`
- `frontend/src/pages/MediaPage.jsx`
- Removed legacy Flask codebase (`opensentry_command/`)

---

Last Updated: April 2026