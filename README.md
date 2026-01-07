# OpenSentry Command Center

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-Web_Framework-000000.svg)](https://flask.palletsprojects.com/)

A web-based command center for monitoring and controlling OpenSentry camera nodes. Provides real-time video streaming, camera discovery via mDNS, and remote control via MQTT.

> **Companion Project:** [OpenSentry Node](https://github.com/yourusername/opensentry-node) - C++/Docker camera streaming node

![OpenSentry Dashboard](https://via.placeholder.com/800x400?text=OpenSentry+Command+Center)

## Features

- **Zero-Config Discovery** - Automatically discovers camera nodes on the local network via mDNS
- **MQTT Control** - Send start/stop/shutdown commands to camera nodes
- **Real-Time Streaming** - View live video feeds from multiple cameras
- **Status Monitoring** - Track camera status with automatic updates
- **Secure by Default** - Web login, MQTT auth, RTSP auth, and rate limiting
- **Docker Ready** - Single command deployment with official uv image

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     OpenSentry Command Center                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │  mdns_discovery  │  │   mqtt_client    │  │ camera_stream │  │
│  │                  │  │                  │  │               │  │
│  │  - Discovery     │  │  - Commands      │  │  - RTSP       │  │
│  │  - Registration  │  │  - Status        │  │  - Frames     │  │
│  └────────┬─────────┘  └────────┬─────────┘  └───────┬───────┘  │
│           │                     │                    │          │
│           └─────────────────────┼────────────────────┘          │
│                                 │                               │
│                    ┌────────────┴────────────┐                  │
│                    │    camera_registry      │                  │
│                    │    (shared state)       │                  │
│                    └────────────┬────────────┘                  │
│                                 │                               │
│                    ┌────────────┴────────────┐                  │
│                    │       server.py         │                  │
│                    │    (Flask routes)       │                  │
│                    └─────────────────────────┘                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
OpenSentry Command/
├── server.py           # Flask web server and routes
├── camera_registry.py  # Shared state (CAMERAS, camera_streams)
├── camera_stream.py    # Persistent RTSP connection management
├── mdns_discovery.py   # mDNS service discovery
├── mqtt_client.py      # MQTT client for commands/status
├── templates/
│   └── index.html      # Web UI template
├── static/
│   ├── css/
│   │   └── styles.css  # Dashboard styling
│   └── js/
│       └── main.js     # Frontend JavaScript
├── pyproject.toml      # Dependencies (uv)
└── README.md
```

## Requirements

- Python 3.10+
- MQTT Broker (e.g., Mosquitto) running on localhost:1883
- OpenSentry Camera Node(s) running on the network

## Installation

```bash
# Clone or navigate to the project
cd "OpenSentry Command"

# Install dependencies with uv
uv sync

# Or with pip
pip install -r requirements.txt
```

## Dependencies

- `flask` - Web framework
- `opencv-python` - Video capture and processing
- `paho-mqtt` - MQTT client
- `zeroconf` - mDNS discovery
- `numpy` - Image processing

## Quick Start (Docker)

### 1. Build and Run

```bash
docker compose up --build
```

### 2. Configure (Optional)

Create a `.env` file to customize credentials:

```bash
# Web UI login
OPENSENTRY_USERNAME=admin
OPENSENTRY_PASSWORD=your_secure_password
SECRET_KEY=your-secret-key

# MQTT authentication (must match Node)
MQTT_USERNAME=opensentry
MQTT_PASSWORD=your_mqtt_password

# RTSP authentication (must match Node)
RTSP_USERNAME=opensentry
RTSP_PASSWORD=your_rtsp_password
```

The web interface will be available at `http://localhost:5000`

**Default credentials (all services):** `opensentry` / `opensentry`

## Usage (Native)

### Start the Command Center

```bash
uv run server.py
```

The web interface will be available at `http://localhost:5000`

### Web Interface

- **Camera Grid** - View all discovered cameras
- **Status Badges** - Real-time status (streaming, idle, offline)
- **Controls** - Start, Pause, Shutdown buttons for each camera

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main web interface |
| `/video_feed/<camera_id>` | GET | MJPEG video stream |
| `/api/cameras` | GET | List all cameras with status |
| `/api/camera/<camera_id>/status` | GET | Get specific camera status |
| `/api/camera/<camera_id>/command` | POST | Send command to camera |

### Commands

```bash
# Start streaming
curl -X POST http://localhost:5000/api/camera/camera1/command \
  -H "Content-Type: application/json" \
  -d '{"command": "start"}'

# Pause streaming
curl -X POST http://localhost:5000/api/camera/camera1/command \
  -H "Content-Type: application/json" \
  -d '{"command": "stop"}'

# Shutdown camera node
curl -X POST http://localhost:5000/api/camera/camera1/command \
  -H "Content-Type: application/json" \
  -d '{"command": "shutdown"}'
```

## How It Works

### Discovery Flow

1. **mDNS (Primary)** - Listens for `_opensentry._tcp` service announcements
2. Camera nodes broadcast their presence with TXT records (camera_id, rtsp_port, etc.)
3. Command Center extracts connection info and starts RTSP stream

4. **MQTT (Fallback)** - If mDNS doesn't find a camera but MQTT receives status messages
5. Auto-registers camera with default RTSP URL

### Communication

- **mDNS** - Zero-config discovery (one-way, node → command center)
- **MQTT** - Bidirectional commands and status updates
  - `opensentry/<camera_id>/status` - Node publishes status
  - `opensentry/<camera_id>/command` - Command center sends commands

## Configuration

Configuration is set in the respective module files:

**mqtt_client.py:**
```python
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_CLIENT_ID = "opensentry_command_center"
```

**mdns_discovery.py:**
```python
MDNS_SERVICE_TYPE = "_opensentry._tcp.local."
```

## Security

OpenSentry Command Center includes multiple layers of security:

| Layer | Protection | Default Credentials |
|-------|-----------|---------------------|
| **Web UI** | Login required + rate limiting | `admin` / `opensentry` |
| **MQTT** | Username/password authentication | `opensentry` / `opensentry` |
| **RTSP** | Username/password authentication | `opensentry` / `opensentry` |

### Rate Limiting

- **5 failed login attempts** triggers a 5-minute lockout
- Attempts are tracked per IP address
- Protects against brute force attacks

### Configuration

All credentials can be customized via environment variables or `.env` file. **Change defaults in production!**

## Companion Project

This Command Center works with the **OpenSentry Node** (C++ camera node) which:
- Captures video from USB cameras
- Streams via RTSP (MediaMTX with authentication)
- Broadcasts presence via mDNS (Avahi)
- Receives commands via MQTT (authenticated)

## Screenshots

*Add screenshots of your running dashboard here*

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see [LICENSE](LICENSE) for details.
