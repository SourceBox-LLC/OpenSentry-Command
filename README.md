# 🛡️ OpenSentry Command Center

**View and control all your security cameras from one dashboard.**

---

## 🚀 Quick Start

### Step 1: Install Docker

**Linux:**
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```
Then log out and back in.

**Mac:** [Download Docker Desktop](https://www.docker.com/products/docker-desktop)

**Windows:** See [Windows Setup (WSL)](#-windows-setup-wsl) below.

---

### Step 2: Download the Project

```bash
git clone https://github.com/SourceBox-LLC/OpenSentry-Command.git
cd OpenSentry-Command
```

---

### Step 3: Run Setup

```bash
chmod +x setup.sh && ./setup.sh
```

You'll see:
```
╔═══════════════════════════════════════════════════════════════╗
║         OpenSentry Command Center - Quick Setup               ║
╚═══════════════════════════════════════════════════════════════╝

✅ Docker found
```

---

### Step 4: Choose Username & Password

The setup will ask you to create login credentials:

```
📝 Let's configure your Command Center...

Choose a username [admin]: admin
Choose a password (min 8 chars): ********
```

---

### Step 5: Save Your Security Secret

A secret key is generated automatically. **Copy this - you'll need it for camera nodes!**

```
╔═══════════════════════════════════════════════════════════════╗
║  IMPORTANT: Copy this secret to your Camera Nodes!            ║
╠═══════════════════════════════════════════════════════════════╣
║  OPENSENTRY_SECRET=7de776c167242fbf10da85c3d182a9fb...        ║
╚═══════════════════════════════════════════════════════════════╝
```

---

### Step 6: Done!

The Command Center starts automatically:

```
🚀 Starting Command Center...

╔═══════════════════════════════════════════════════════════════╗
║                    Setup Complete!                            ║
╠═══════════════════════════════════════════════════════════════╣
║  Dashboard:  http://localhost:5000                            ║
║  Username:   admin                                            ║
║  Password:   ********                                         ║
╠═══════════════════════════════════════════════════════════════╣
║  Commands:                                                    ║
║    View logs:    docker compose logs -f                       ║
║    Stop:         docker compose down                          ║
║    Restart:      docker compose restart                       ║
╚═══════════════════════════════════════════════════════════════╝
```

**Open http://localhost:5000** and log in. 🎉

---

## 📷 Adding Cameras

Set up [OpenSentry Camera Nodes](https://github.com/SourceBox-LLC/OpenSentry-Node) on your network.

**Important:** When setting up camera nodes, use the same `OPENSENTRY_SECRET` shown during Command Center setup.

Cameras auto-discover within 30 seconds.

---

## 🎮 Dashboard Controls

| Button | Action |
|--------|--------|
| **▶ Start** | Start video stream |
| **⏸ Pause** | Pause stream |
| **⏻ Shutdown** | Turn off camera |

| Status | Meaning |
|--------|---------|
| 🟢 Streaming | Camera active |
| 🟡 Idle | Paused |
| 🔴 Offline | Not responding |

---

## 🔧 Common Commands

```bash
# View logs
docker compose logs -f

# Stop
docker compose down

# Restart
docker compose restart

# Update
git pull && docker compose up --build -d
```

---

## ❓ Troubleshooting

| Problem | Solution |
|---------|----------|
| **No cameras showing** | Check both devices are on same WiFi. Wait 30 seconds. |
| **Can't log in** | Default: `admin` / `opensentry`. Check `.env` file. |
| **Account locked** | Wait 5 minutes. |
| **Port 5000 in use** | Stop other app or edit port in `docker-compose.yml` |

**Still stuck?** Run `docker compose logs -f` and check for errors.

---

## ⚙️ Configuration

Edit `.env` file (created by setup script):

```bash
# Login
OPENSENTRY_USERNAME=admin
OPENSENTRY_PASSWORD=your-password

# Security (must match camera nodes!)
OPENSENTRY_SECRET=your-secret-key

# Session timeout (minutes)
SESSION_TIMEOUT=30
```

After changes: `docker compose down && docker compose up -d`

---

## 🪟 Windows Setup (WSL)

Windows users can run OpenSentry using WSL (Windows Subsystem for Linux).

### Step 1: Install WSL

Open **PowerShell as Administrator** and run:

```powershell
wsl --install
```

Restart your computer when prompted.

### Step 2: Set Up Ubuntu

After restart, Ubuntu will open automatically. Create a username and password when asked.

### Step 3: Install Docker in WSL

In the Ubuntu terminal:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

Close and reopen Ubuntu.

### Step 4: Follow Quick Start

Now follow **Steps 2-6** from the [Quick Start](#-quick-start) section above.

```bash
git clone https://github.com/SourceBox-LLC/OpenSentry-Command.git
cd OpenSentry-Command
chmod +x setup.sh && ./setup.sh
```

**Access the dashboard at http://localhost:5000** from your Windows browser.

---

## 📜 License

MIT - Free for personal and commercial use.

---

**[OpenSentry Node](https://github.com/SourceBox-LLC/OpenSentry-Node)** · Made with ❤️ by the OpenSentry Team
