# 🛡️ OpenSentry Command Center

**View and control all your security cameras from one dashboard.**

---

## 🚀 Quick Start

### 1. Install Docker

**Windows/Mac:** [Download Docker Desktop](https://www.docker.com/products/docker-desktop)

**Linux:**
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in
```

### 2. Download & Run

```bash
git clone https://github.com/SourceBox-LLC/OpenSentry-Command.git
cd OpenSentry-Command
chmod +x setup.sh && ./setup.sh
```

### 3. Open Dashboard

Go to **http://localhost:5000** and log in.

**Done!** 🎉 Your cameras will appear automatically.

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

## 📜 License

MIT - Free for personal and commercial use.

---

**[OpenSentry Node](https://github.com/SourceBox-LLC/OpenSentry-Node)** · Made with ❤️ by the OpenSentry Team
