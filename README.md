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
│   │   ├── cameras.py      # Camera CRUD, settings, alerts
│   │   ├── hls.py          # HLS playlist/segment serving
│   │   ├── nodes.py        # CloudNode registration, heartbeat
│   │   ├── streams.py      # Upload URL generation, cleanup
│   │   ├── audit.py        # Stream access logs
│   │   └── webhooks.py     # Clerk webhooks
│   ├── core/
│   │   ├── auth.py         # Clerk JWT verification, permissions
│   │   ├── config.py       # Settings from environment
│   │   ├── database.py     # SQLAlchemy setup
│   │   └── clerk.py        # Clerk client
│   ├── models/
│   │   └── models.py       # SQLAlchemy models
│   ├── schemas/
│   │   └── schemas.py      # Pydantic request/response schemas
│   ├── services/
│   │   └── storage.py      # Tigris/S3 operations
│   └── main.py             # FastAPI app entry
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
│   │   ├── AdminPage.jsx     # Stream logs
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
| POST | `/api/settings/notifications` | Update notification settings |
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