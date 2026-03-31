# 🛡️ OpenSentry Command Center

**View and control all your security cameras from one dashboard with real-time detection alerts.**

**Built with FastAPI + React + Clerk Authentication**

**🔒 Fully Encrypted:** HTTPS web UI, RTSPS video streams, MQTT over TLS  
**🎯 Smart Detection:** Motion, face, and object detection with real-time alerts  
**👥 Organization-Based:** Multi-tenant with role-based access control via Clerk

---

## 🚀 Quick Start (Development Mode)

The fastest way to get started is using **Development Mode**, which requires no authentication setup.

### Prerequisites

- **Node.js** >= 18
- **Python** >= 3.10
- **uv** (Python package manager)

### 1. Backend Setup

```bash
cd backend

# Copy environment file
cp .env.example .env

# Install dependencies
uv sync

# Run development server (DEV_MODE=true by default)
uv run python start.py
```

The API will be available at `http://localhost:8000`

You'll see:
```
🚀 OpenSentry Command Center started (DEV MODE - No auth required)
   DEV_USER_ID: dev-user-123
   DEV_ORG_ID: dev-org-123
```

### 2. Frontend Setup

```bash
cd frontend

# Copy environment file (leave VITE_CLERK_PUBLISHABLE_KEY empty for dev mode)
cp .env.example .env

# Install dependencies
npm install

# Run development server
npm run dev
```

The app will be available at `http://localhost:5173`

**No Clerk account or API keys needed!** The app runs with a mock user and organization.

---

## 🔐 Production Setup (Clerk Authentication)

For production with multi-tenant authentication, set up Clerk:

### 1. Create a Clerk Account

1. Go to [clerk.com](https://clerk.com) and create an account
2. Create a new application
3. Enable Organizations
4. Copy your **Publishable Key** and **Secret Key**
5. Set up a webhook endpoint for subscription events (optional for billing)

### 2. Configure Backend

```bash
cd backend

# Edit .env
CLERK_SECRET_KEY=your_secret_key
CLERK_PUBLISHABLE_KEY=your_publishable_key
CLERK_JWKS_URL=https://your-instance.clerk.accounts.dev/.well-known/jwks.json
CLERK_WEBHOOK_SECRET=your_webhook_secret
DEV_MODE=false

# Install with Clerk support
uv sync --extra clerk

# Run server
uv run python start.py
```

### 3. Configure Frontend

```bash
cd frontend

# Edit .env
VITE_CLERK_PUBLISHABLE_KEY=your_publishable_key
VITE_API_URL=http://localhost:8000

npm run dev
```

---

## 🏗️ Architecture

### System Architecture

```
Browser (localhost:5173) → Backend (localhost:8000) ← ngrok ← Rust Camera Nodes (external)
```

**Key Points:**
- Frontend talks directly to backend on same machine (no CORS issues)
- ngrok is ONLY for external Rust camera nodes to reach the backend
- `VITE_API_URL` should be `http://localhost:8000` (not ngrok URL)

### Frontend
- **React 19** - UI framework
- **Vite** - Build tool
- **React Router** - Client-side routing
- **Clerk** - Authentication & organization management (optional)
- **CSS** - Styling

### Backend
- **FastAPI** - Python web framework
- **SQLAlchemy** - ORM
- **SQLite** - Database (development)
- **Clerk Backend API** - Auth verification (optional)
- **Svix** - Webhook handling

### CloudNode (Rust)
- **OpenSentry CloudNode** - Local camera capture and streaming
- Captures USB camera video
- Streams to cloud Command Center via HTTPS
- Auto-registers cameras on first connection

---

## 🔑 Environment Variables

### Backend (.env)

```env
# Development Mode (set to "false" for production with Clerk)
DEV_MODE=true
DEV_USER_ID=dev-user-123
DEV_USER_EMAIL=dev@example.com
DEV_ORG_ID=dev-org-123

# Clerk Authentication (leave empty for DEV_MODE=true)
CLERK_SECRET_KEY=
CLERK_PUBLISHABLE_KEY=
CLERK_JWKS_URL=
CLERK_WEBHOOK_SECRET=

# Database
DATABASE_URL=sqlite:///./opensentry.db

# Frontend URL (for CORS)
FRONTEND_URL=http://localhost:5173

# OpenSentry Security Secret (for camera node authentication)
OPENSENTRY_SECRET=your_secret_key_here

# MQTT Configuration
MQTT_BROKER=localhost
MQTT_PORT=1883
MQTT_USE_TLS=false
MQTT_USERNAME=opensentry
MQTT_PASSWORD=opensentry

# RTSP Credentials
RTSP_USERNAME=opensentry
RTSP_PASSWORD=opensentry

# Session timeout (minutes)
SESSION_TIMEOUT=30
```

### Frontend (.env)

```env
# Leave empty for Development Mode
# VITE_CLERK_PUBLISHABLE_KEY=your_clerk_publishable_key

# Backend API URL
VITE_API_URL=http://localhost:8000
```

---

## 📷 Adding Cameras

### Cloud-Hosted Mode (Production)

1. **Create a Camera Node:**
   - Go to Settings → Camera Nodes
   - Click "Add Node"
   - Enter a name (e.g., "Home", "Office")
   - Copy the Node ID and API key

2. **Run the Rust CloudNode:**
   ```bash
   cargo run -- \
     --node-id <your-node-id> \
     --api-key <your-api-key> \
     --api-url https://your-ngrok-url.ngrok-free.dev
   ```

3. **Cameras auto-register** when the CloudNode connects with USB cameras

### Local Mode (Development)

1. Cameras auto-discover within 30 seconds when OpenSentry Camera Nodes are on the same network via mDNS
2. Control cameras from the dashboard (start, stop, record, snapshot)

---

## 🎯 Features

### Camera Management
- **Live Streaming** - View all cameras in real-time
- **Recording** - Start/stop video recordings
- **Snapshots** - Capture still images
- **Detection Events** - Motion, face, and object detection

### Organization-Based Access
- Multiple organizations (managed via Clerk)
- Role-based permissions
- Multi-tenant data isolation

### Media Library
- View saved snapshots and recordings
- Download or delete media
- Automatic H.264 transcoding for browser playback

---

## 📁 Project Structure

```
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── api/               # API routes
│   │   │   ├── cameras.py     # Camera endpoints
│   │   │   ├── video.py      # Video streaming
│   │   │   └── webhooks.py    # Clerk webhooks
│   │   ├── core/             # Core modules
│   │   │   ├── config.py     # Configuration
│   │   │   ├── database.py   # Database setup
│   │   │   ├── auth.py       # Authentication
│   │   │   └── clerk.py      # Clerk client
│   │   ├── models/           # SQLAlchemy models
│   │   │   └── models.py
│   │   ├── schemas/          # Pydantic schemas
│   │   │   └── schemas.py
│   │   ├── services/         # Business logic
│   │   │   ├── camera.py     # Camera streaming
│   │   │   ├── mqtt.py       # MQTT client
│   │   │   └── discovery.py  # mDNS discovery
│   │   └── main.py           # FastAPI app
│   ├── .env.example
│   └── pyproject.toml
│
├── frontend/                   # React frontend
│   ├── src/
│   │   ├── components/       # Reusable UI components
│   │   │   ├── Layout.jsx
│   │   │   └── CameraCard.jsx
│   │   ├── hooks/            # Custom React hooks
│   │   │   ├── useDevMode.jsx
│   │   │   ├── useAuthCompat.jsx
│   │   │   └── useOrganizationCompat.jsx
│   │   ├── pages/            # Page components
│   │   │   ├── HomePage.jsx
│   │   │   ├── DashboardPage.jsx
│   │   │   ├── SettingsPage.jsx
│   │   │   └── MediaPage.jsx
│   │   ├── services/         # API client
│   │   │   └── api.js
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── index.css
│   ├── .env.example
│   ├── package.json
│   └── vite.config.js
│
└── README.md
```

---

## 📡 API Endpoints

### Cameras
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/cameras` | List all cameras with status |
| GET | `/api/camera/{id}/status` | Get specific camera status |
| POST | `/api/camera/{id}/command` | Send command (start/stop/shutdown) |
| DELETE | `/api/camera/{id}/forget` | Remove camera from system |
| GET | `/api/camera/{id}/snapshot` | Take a snapshot |
| POST | `/api/camera/{id}/recording/start` | Start recording |
| POST | `/api/camera/{id}/recording/stop` | Stop recording |

### Media
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/snapshots` | List all snapshots |
| GET | `/api/snapshots/{id}` | Download snapshot |
| DELETE | `/api/snapshots/{id}` | Delete snapshot |
| GET | `/api/recordings` | List all recordings |
| GET | `/api/recordings/{id}` | Stream/download recording |
| DELETE | `/api/recordings/{id}` | Delete recording |

### Settings
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/settings` | Get all settings |
| GET | `/api/settings/recording` | Get recording settings |
| POST | `/api/settings/recording` | Update recording settings |
| GET | `/api/settings/notifications` | Get notification settings |
| POST | `/api/settings/notifications` | Update notification settings |

### Webhooks
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/webhooks/clerk` | Handle Clerk webhook events |

### Camera Nodes
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/nodes` | List all nodes for organization |
| POST | `/api/nodes` | Create a new camera node |
| GET | `/api/nodes/{id}` | Get node details |
| DELETE | `/api/nodes/{id}` | Delete a node |
| POST | `/api/nodes/{id}/generate-key` | Regenerate API key |
| POST | `/api/nodes/register` | Register node (Rust CloudNode) |
| POST | `/api/nodes/heartbeat` | Node heartbeat (Rust CloudNode) |

---

## 🔒 Permissions

Clerk organizations support custom permissions (V2 format):

| Permission Key | Description |
|----------------|-------------|
| `org:admin:admin` | Full admin access |
| `org:cameras:manage_cameras` | Manage cameras and nodes |
| `org:cameras:view_cameras` | View cameras and live feeds |

**Important:** Permissions use the V2 format `org:{feature}:{permission}`. See AGENTS.md for complete Clerk setup instructions.

---

## 🎨 Development

### Backend

```bash
cd backend
uv run python start.py     # Development server
uv run uvicorn app.main:app --reload  # Alternative
```

### Frontend

```bash
cd frontend
npm run dev     # Development server
npm run build   # Production build
npm run lint    # Lint code
```

---

## 📜 License

MIT - Free for personal and commercial use.

---

**Built with ❤️ using FastAPI, React, and Clerk**