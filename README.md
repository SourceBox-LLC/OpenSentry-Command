# 🛡️ OpenSentry Command Center

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](https://www.docker.com/)

**Your central hub for viewing and controlling all your OpenSentry security cameras.**

---

## 📖 Table of Contents

1. [What is OpenSentry Command Center?](#-what-is-opensentry-command-center)
2. [What You Need Before Starting](#-what-you-need-before-starting)
3. [Quick Start Guide (5 Minutes)](#-quick-start-guide-5-minutes)
4. [Setting Up Security (Important!)](#-setting-up-security-important)
5. [Using the Dashboard](#-using-the-dashboard)
6. [Troubleshooting](#-troubleshooting)
7. [Advanced Configuration](#-advanced-configuration)
8. [Project Structure](#-project-structure)
9. [Getting Help](#-getting-help)

---

## 🎯 What is OpenSentry Command Center?

OpenSentry Command Center is a **web-based dashboard** that lets you:

- ✅ **View live video** from all your cameras in one place
- ✅ **Control cameras** remotely (start, pause, shutdown)
- ✅ **Auto-discover cameras** on your network (no manual setup needed)
- ✅ **Monitor status** of each camera in real-time

**Think of it like this:** If OpenSentry Camera Nodes are your security cameras, then the Command Center is your security guard station where you can see all the feeds.

### How It Works (Simple Version)

```
Your Cameras (Nodes)          Command Center              You
    📷 📷 📷         ──────►      🖥️           ──────►    👁️
                     
  Cameras broadcast           Command Center              You view
  "I'm here!" on the          finds them and             everything in
  network automatically       shows their video          your browser
```

---

## 📋 What You Need Before Starting

### Required

| Item | Description | How to Check |
|------|-------------|--------------|
| **Docker Desktop** | Software that runs the Command Center | Open terminal, type `docker --version` |
| **At least 1 OpenSentry Node** | A camera node running on your network | Should be already set up and running |
| **Same Network** | Command Center and Nodes must be on the same WiFi/network | Both devices connected to same router |

### Don't Have Docker?

**Windows/Mac:** Download from [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)

**Linux:**
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in after this
```

---

## 🚀 Quick Start Guide (2 Minutes)

### Step 1: Download the Project

```bash
git clone https://github.com/SourceBox-LLC/OpenSentry-Command.git
cd OpenSentry-Command
```

### Step 2: Run the Setup Script

```bash
chmod +x setup.sh
./setup.sh
```

**That's it!** The script will:
- Ask you for a username and password
- Generate a security secret automatically
- Start the Command Center

### What You'll See

```
╔═══════════════════════════════════════════════════════════════╗
║                    Setup Complete!                            ║
╠═══════════════════════════════════════════════════════════════╣
║  Dashboard:  http://localhost:5000                            ║
║  Username:   admin                                            ║
╚═══════════════════════════════════════════════════════════════╝
[mDNS] Discovery started, listening for OpenSentry nodes...
[MQTT] Client started
```

### Step 3: Open the Dashboard

1. Open your web browser (Chrome, Firefox, Edge, Safari)
2. Go to: **http://localhost:5000**
3. You'll see a login page

### Step 4: Log In

Use the default credentials:

| Field | Value |
|-------|-------|
| **Username** | `admin` |
| **Password** | `opensentry` |

⚠️ **Change these in production!** (See [Security Setup](#-setting-up-security-important))

### Step 5: View Your Cameras

Once logged in, you'll see:
- 📡 A "Discovering..." message if no cameras are found yet
- 📹 Camera cards with live video feeds once cameras are discovered

**That's it! You're up and running!** 🎉

---

## 🔐 Setting Up Security (Important!)

The default password is `opensentry` - **anyone who knows this can access your cameras!**

### Step 1: Create a Configuration File

Create a file called `.env` in the project folder:

**Windows (PowerShell):**
```powershell
New-Item .env -ItemType File
notepad .env
```

**Mac/Linux:**
```bash
touch .env
nano .env
```

### Step 2: Add Your Settings

Copy and paste this into the `.env` file:

```bash
# ============================================
# OPENSENTRY COMMAND CENTER CONFIGURATION
# ============================================

# LOGIN CREDENTIALS
# Change these to something only you know!
OPENSENTRY_USERNAME=admin
OPENSENTRY_PASSWORD=MySecurePassword123!

# SECURITY SECRET (IMPORTANT!)
# This must be the SAME on Command Center AND all Camera Nodes
# Generate a random one with: python -c "import secrets; print(secrets.token_hex(32))"
OPENSENTRY_SECRET=paste-your-64-character-secret-here

# SESSION TIMEOUT (optional)
# How many minutes before you need to log in again (default: 30)
SESSION_TIMEOUT=30
```

### Step 3: Generate a Secure Secret

Run this command to generate a random secret:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**Example output:** `a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456`

Copy this and paste it after `OPENSENTRY_SECRET=`

### Step 4: Use the Same Secret on Your Camera Nodes

**Important:** The `OPENSENTRY_SECRET` must be **identical** on:
- ✅ The Command Center (this project)
- ✅ Every Camera Node you want to connect

If they don't match, cameras won't connect!

### Step 5: Restart with New Settings

```bash
docker compose down
docker compose up --build
```

---

## 🖥️ Using the Dashboard

### Main Screen Overview

```
┌─────────────────────────────────────────────────────────────┐
│  🛡️ OpenSentry          [MQTT: Connected] [2 Nodes Online] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   Active Cameras: 2    Total Nodes: 2    Streaming: 2      │
│                                                             │
│   ┌─────────────────┐   ┌─────────────────┐                │
│   │  📹 Kitchen     │   │  📹 Front Door  │                │
│   │  ┌───────────┐  │   │  ┌───────────┐  │                │
│   │  │  VIDEO    │  │   │  │  VIDEO    │  │                │
│   │  │  FEED     │  │   │  │  FEED     │  │                │
│   │  └───────────┘  │   │  └───────────┘  │                │
│   │  [▶Start] [⏸] [⏻]│   │  [▶Start] [⏸] [⏻]│               │
│   └─────────────────┘   └─────────────────┘                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Camera Status Colors

| Color | Status | Meaning |
|-------|--------|---------|
| 🟢 Green | `streaming` | Camera is working and sending video |
| 🟡 Yellow | `idle` | Camera is connected but paused |
| 🔴 Red | `offline` | Camera is not responding |
| ⚪ Gray | `discovered` | Camera found, connecting... |

### Control Buttons

| Button | What It Does |
|--------|--------------|
| **▶ Start** | Start streaming video from this camera |
| **⏸ Pause** | Pause the video stream (camera stays on) |
| **⏻ Shutdown** | Turn off the camera node completely |

### Top Status Bar

- **MQTT:** Shows connection to the message system (should be "Connected")
- **Nodes Online:** Number of cameras currently connected

---

## 🔧 Troubleshooting

### ❌ "Cannot connect to Docker daemon"

**Problem:** Docker isn't running.

**Fix:**
1. Open Docker Desktop application
2. Wait for it to fully start (icon in taskbar/menu bar)
3. Try the command again

---

### ❌ No cameras showing up

**Problem:** Cameras aren't being discovered.

**Checklist:**
1. ✅ Is the Camera Node running? (Check with `docker ps` on that device)
2. ✅ Are both devices on the same network/WiFi?
3. ✅ Is the `OPENSENTRY_SECRET` the same on both?
4. ✅ Wait 30 seconds - discovery can take a moment

**Debug command:**
```bash
docker compose logs -f
```
Look for lines like `[mDNS] Discovered service:` or `[MQTT] Connected`

---

### ❌ "Invalid username or password"

**Problem:** Wrong login credentials.

**Fix:**
- Default is `admin` / `opensentry`
- If you changed it, check your `.env` file
- Restart after changing: `docker compose down && docker compose up`

---

### ❌ "Account locked" message

**Problem:** Too many failed login attempts.

**Fix:** Wait 5 minutes. The lockout will automatically expire.

---

### ❌ Camera shows "Connecting..." forever

**Problem:** Video stream isn't connecting.

**Possible causes:**
1. **Network issue** - Camera and Command Center can't reach each other
2. **Wrong credentials** - OPENSENTRY_SECRET doesn't match
3. **Firewall** - Port 8554 (RTSP) might be blocked

**Fix:** Check camera node logs for errors:
```bash
# On the device running the camera node
docker compose logs -f
```

---

### ❌ Port 5000 already in use

**Problem:** Another application is using port 5000.

**Fix - Option 1:** Stop the other application

**Fix - Option 2:** Change the port in `docker-compose.yml`:
```yaml
ports:
  - "8080:5000"  # Change 5000 to 8080 or any free port
```
Then access via `http://localhost:8080`

---

## ⚙️ Advanced Configuration

### All Configuration Options

Create a `.env` file with any of these settings:

```bash
# =============================================
# COMPLETE CONFIGURATION REFERENCE
# =============================================

# --- LOGIN ---
OPENSENTRY_USERNAME=admin          # Web UI username
OPENSENTRY_PASSWORD=opensentry     # Web UI password

# --- SECURITY ---
OPENSENTRY_SECRET=your-64-char-secret  # Shared secret for all nodes

# --- SESSION ---
SESSION_TIMEOUT=30                 # Minutes until auto-logout (default: 30)

# --- MQTT (rarely need to change) ---
MQTT_BROKER=localhost              # MQTT server address
MQTT_PORT=1883                     # MQTT server port

# --- LEGACY MODE (only if not using OPENSENTRY_SECRET) ---
MQTT_USERNAME=opensentry
MQTT_PASSWORD=mqtt-password
RTSP_USERNAME=opensentry
RTSP_PASSWORD=rtsp-password
```

### Running Without Docker

If you prefer to run natively:

```bash
# Install Python 3.10+ first, then:
cd "OpenSentry Command"

# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Run
uv run run.py
```

### Accessing from Other Devices

By default, the dashboard is accessible from any device on your network:

1. Find your computer's IP address:
   - **Windows:** Open CMD, type `ipconfig`, look for "IPv4 Address"
   - **Mac:** System Preferences → Network → shows IP
   - **Linux:** `ip addr` or `hostname -I`

2. From another device, open: `http://YOUR_IP:5000`

Example: `http://192.168.1.100:5000`

---

## 📁 Project Structure

```
OpenSentry Command/
│
├── 📄 run.py                    # Main entry point
├── 📄 docker-compose.yml        # Docker configuration
├── 📄 Dockerfile                # Container build instructions
├── 📄 .env.example              # Example configuration
├── 📄 pyproject.toml            # Python dependencies
│
└── 📂 opensentry_command/       # Main application code
    ├── 📄 __init__.py           # Application factory
    ├── 📄 config.py             # Configuration settings
    │
    ├── 📂 auth/                 # Login & security
    │   └── 📄 handlers.py       # Authentication logic
    │
    ├── 📂 models/               # Data storage
    │   └── 📄 camera.py         # Camera registry
    │
    ├── 📂 routes/               # Web pages & API
    │   ├── 📄 main.py           # Main pages (login, dashboard)
    │   └── 📄 api.py            # REST API endpoints
    │
    ├── 📂 services/             # Background services
    │   ├── 📄 camera.py         # Video streaming
    │   ├── 📄 discovery.py      # Camera discovery (mDNS)
    │   └── 📄 mqtt.py           # Command messaging
    │
    ├── 📂 static/               # CSS, JavaScript, images
    │   ├── 📂 css/
    │   └── 📂 js/
    │
    └── 📂 templates/            # HTML pages
        ├── 📄 index.html        # Main dashboard
        └── 📄 login.html        # Login page
```

---

## 🆘 Getting Help

### Still stuck?

1. **Check the logs:**
   ```bash
   docker compose logs -f
   ```

2. **Search existing issues:** [GitHub Issues](https://github.com/SourceBox-LLC/OpenSentry-Command/issues)

3. **Open a new issue:** Include:
   - What you tried to do
   - What happened instead
   - The output of `docker compose logs`

### Related Projects

- **[OpenSentry Node](https://github.com/SourceBox-LLC/OpenSentry-Node)** - The camera node software

---

## 📜 License

MIT License - Free for personal and commercial use.

See [LICENSE](LICENSE) for full details.

---

<div align="center">

**Made with ❤️ by the OpenSentry Team**

</div>
