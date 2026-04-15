#!/bin/bash
set -euo pipefail

# OpenSentry CloudNode Installer
# Usage: curl -fsSL https://opensentry-command.fly.dev/install.sh | bash

# ── Colors ──────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

REPO="SourceBox-LLC/opensentry-cloud-node"
INSTALL_DIR="${OPENSENTRY_INSTALL_DIR:-$HOME/.opensentry}"

# ── Banner ──────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}  OpenSentry CloudNode Installer${NC}"
echo -e "${DIM}  ================================${NC}"
echo ""

# ── Detect platform ────────────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
    Linux*)  PLATFORM="linux" ;;
    Darwin*) PLATFORM="macos" ;;
    *)
        echo -e "${RED}Error: Unsupported operating system: $OS${NC}"
        echo "For Windows, use PowerShell:"
        echo "  irm https://opensentry-command.fly.dev/install.ps1 | iex"
        exit 1
        ;;
esac

case "$ARCH" in
    x86_64|amd64)  ARCH="x86_64" ;;
    aarch64|arm64) ARCH="aarch64" ;;
    armv7*)        ARCH="armv7" ;;
    *)
        echo -e "${RED}Error: Unsupported architecture: $ARCH${NC}"
        exit 1
        ;;
esac

echo -e "  Platform:  ${CYAN}${PLATFORM}-${ARCH}${NC}"
echo -e "  Install:   ${CYAN}${INSTALL_DIR}${NC}"
echo ""

# ── Check dependencies ─────────────────────────────────────────────
check_cmd() {
    if ! command -v "$1" &>/dev/null; then
        return 1
    fi
    return 0
}

if ! check_cmd curl; then
    echo -e "${RED}Error: curl is required but not installed.${NC}"
    exit 1
fi

# ── Try downloading pre-built binary ───────────────────────────────
LATEST_URL="https://api.github.com/repos/${REPO}/releases/latest"

echo -e "${DIM}Checking for pre-built release...${NC}"

DOWNLOAD_URL=""
RELEASE_TAG=""

if RELEASE_JSON=$(curl -fsSL "$LATEST_URL" 2>/dev/null); then
    # NOTE: these pipelines end in `grep` which returns 1 if it finds nothing.
    # Under `set -o pipefail`, that exit code propagates out of the $(...)
    # and, because we're assigning to a variable, `set -e` would silently
    # abort the entire script. The `|| true` keeps us alive so we can fall
    # through to the source-build path when there's no matching binary
    # (e.g. linux-aarch64 users hitting a release that only ships x86_64).
    RELEASE_TAG=$(echo "$RELEASE_JSON" | grep '"tag_name"' | head -1 | sed 's/.*"tag_name": *"//;s/".*//' || true)

    # Look for matching binary in release assets
    ASSET_PATTERN="${PLATFORM}.*${ARCH}"
    DOWNLOAD_URL=$(echo "$RELEASE_JSON" | grep -o '"browser_download_url": "[^"]*'"${ASSET_PATTERN}"'[^"]*"' | head -1 | sed 's/"browser_download_url": "//;s/"$//' || true)

    if [ -z "$DOWNLOAD_URL" ] && [ -n "$RELEASE_TAG" ]; then
        echo -e "  Release ${CYAN}${RELEASE_TAG}${NC} found, but no ${CYAN}${PLATFORM}-${ARCH}${NC} binary in its assets."
    fi
fi

if [ -n "$DOWNLOAD_URL" ]; then
    echo -e "${GREEN}Found release ${RELEASE_TAG}${NC}"
    echo -e "${DIM}Downloading...${NC}"

    mkdir -p "$INSTALL_DIR"
    TMPFILE=$(mktemp)

    if curl -fsSL "$DOWNLOAD_URL" -o "$TMPFILE"; then
        # Detect archive type and extract
        case "$DOWNLOAD_URL" in
            *.tar.gz|*.tgz)
                tar -xzf "$TMPFILE" -C "$INSTALL_DIR"
                ;;
            *.zip)
                if check_cmd unzip; then
                    unzip -qo "$TMPFILE" -d "$INSTALL_DIR"
                else
                    echo -e "${RED}Error: unzip is required to extract this release.${NC}"
                    rm -f "$TMPFILE"
                    exit 1
                fi
                ;;
            *)
                # Assume raw binary
                cp "$TMPFILE" "$INSTALL_DIR/opensentry-cloudnode"
                ;;
        esac

        rm -f "$TMPFILE"
        chmod +x "$INSTALL_DIR/opensentry-cloudnode" 2>/dev/null || true

        echo -e "${GREEN}Downloaded successfully.${NC}"
    else
        echo -e "${YELLOW}Download failed. Falling back to source build...${NC}"
        DOWNLOAD_URL=""
    fi
fi

# ── Fall back to building from source ──────────────────────────────
if [ -z "$DOWNLOAD_URL" ]; then
    echo -e "${YELLOW}No pre-built binary available. Building from source...${NC}"
    echo ""

    # Check build dependencies
    MISSING=""
    if ! check_cmd git; then MISSING="$MISSING git"; fi
    if ! check_cmd cargo; then MISSING="$MISSING cargo(rust)"; fi

    if [ -n "$MISSING" ]; then
        echo -e "${RED}Missing required tools:${MISSING}${NC}"
        echo ""
        if echo "$MISSING" | grep -q "cargo"; then
            echo -e "Install Rust: ${CYAN}curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh${NC}"
        fi
        if echo "$MISSING" | grep -q "git"; then
            if [ "$PLATFORM" = "linux" ]; then
                echo -e "Install git:  ${CYAN}sudo apt install git${NC}"
            elif [ "$PLATFORM" = "macos" ]; then
                echo -e "Install git:  ${CYAN}xcode-select --install${NC}"
            fi
        fi
        exit 1
    fi

    mkdir -p "$INSTALL_DIR"
    CLONE_DIR="$INSTALL_DIR/source"

    if [ -d "$CLONE_DIR" ]; then
        echo -e "${DIM}Updating existing source...${NC}"
        git -C "$CLONE_DIR" pull --quiet
    else
        echo -e "${DIM}Cloning repository...${NC}"
        git clone --quiet "https://github.com/${REPO}.git" "$CLONE_DIR"
    fi

    echo -e "${DIM}Building (this may take a few minutes)...${NC}"
    (cd "$CLONE_DIR" && cargo build --release --quiet)

    cp "$CLONE_DIR/target/release/opensentry-cloudnode" "$INSTALL_DIR/opensentry-cloudnode"
    chmod +x "$INSTALL_DIR/opensentry-cloudnode"

    echo -e "${GREEN}Build complete.${NC}"
fi

# ── Check for ffmpeg ───────────────────────────────────────────────
echo ""
if check_cmd ffmpeg; then
    FFMPEG_VERSION=$(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')
    echo -e "  ffmpeg:    ${GREEN}${FFMPEG_VERSION} (installed)${NC}"
else
    echo -e "  ffmpeg:    ${YELLOW}not found${NC}"
    echo ""
    echo -e "${YELLOW}CloudNode requires ffmpeg for video processing.${NC}"

    # The script is usually run via `curl | bash`, so stdin is the pipe
    # from curl, not a terminal. Reading from /dev/tty is how we still
    # get an interactive yes/no from the operator — skip silently if
    # the controlling terminal isn't available (CI, container build).
    prompt_install_ffmpeg() {
        local prompt_msg="$1"
        local install_cmd="$2"
        if [ ! -t 1 ] || [ ! -r /dev/tty ]; then
            # No tty — print the manual command and bail.
            echo -e "  Install:  ${CYAN}${install_cmd}${NC}"
            return 1
        fi
        # Prompt default is "yes" — operators running the installer
        # almost always want ffmpeg; making them type "y" every time is
        # friction without safety. They can still say no.
        local reply=""
        printf "  %b " "${prompt_msg} [Y/n]:"
        read -r reply </dev/tty || reply="n"
        case "${reply:-y}" in
            y|Y|yes|YES) return 0 ;;
            *)
                echo -e "  ${DIM}Skipping — install manually: ${CYAN}${install_cmd}${NC}"
                return 1
                ;;
        esac
    }

    if [ "$PLATFORM" = "linux" ]; then
        # apt is the common case (Debian/Ubuntu/Raspberry Pi OS). Fall
        # back to just printing the command on other distros — trying to
        # auto-detect dnf/pacman/apk etc. is more footgun than win.
        if check_cmd apt-get; then
            if prompt_install_ffmpeg "Install ffmpeg now with sudo apt install?" "sudo apt install ffmpeg"; then
                echo -e "  ${DIM}Running: sudo apt-get install -y ffmpeg${NC}"
                if sudo apt-get update -qq && sudo apt-get install -y ffmpeg; then
                    echo -e "  ffmpeg:    ${GREEN}installed${NC}"
                else
                    echo -e "  ${RED}apt install failed — install manually and re-run setup.${NC}"
                fi
            fi
        else
            echo -e "  Install:  ${CYAN}sudo apt install ffmpeg${NC}  ${DIM}(or your distro's equivalent)${NC}"
        fi
    elif [ "$PLATFORM" = "macos" ]; then
        if check_cmd brew; then
            if prompt_install_ffmpeg "Install ffmpeg now with Homebrew?" "brew install ffmpeg"; then
                echo -e "  ${DIM}Running: brew install ffmpeg${NC}"
                if brew install ffmpeg; then
                    echo -e "  ffmpeg:    ${GREEN}installed${NC}"
                else
                    echo -e "  ${RED}brew install failed — install manually and re-run setup.${NC}"
                fi
            fi
        else
            echo -e "  Install:  ${CYAN}brew install ffmpeg${NC}  ${DIM}(install Homebrew first from https://brew.sh)${NC}"
        fi
    fi
fi

# ── Offer systemd auto-start on Linux ─────────────────────────────
# Only fires on Linux + systemd + interactive TTY. Skips on WSL, Docker,
# CI, and anywhere without /dev/tty so the one-liner stays safe to run
# in automated contexts. Always opt-in — never flips anything on silently.
install_systemd_service() {
    local svc_name="opensentry-cloudnode"
    local svc_file="/etc/systemd/system/${svc_name}.service"
    local run_user="${SUDO_USER:-$USER}"

    # Render the unit file to a temp location first so we can inspect it
    # if the install step fails, and so the sudo move is the only
    # privileged action. Keeps blast-radius tiny.
    local tmp_unit
    tmp_unit=$(mktemp) || return 1

    cat >"$tmp_unit" <<UNIT
[Unit]
Description=OpenSentry CloudNode
Documentation=https://opensentry-command.fly.dev
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${run_user}
# 'video' is the standard group that owns /dev/video* on Debian/Ubuntu
# /Raspberry Pi OS — the CloudNode needs it to open USB cameras.
SupplementaryGroups=video
# Inherit a sane PATH so ffmpeg (installed via apt above) is found even
# when systemd's default PATH is missing /usr/local/bin.
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/opensentry-cloudnode
StandardOutput=journal
StandardError=journal
Restart=on-failure
RestartSec=5s
# If the service fails to start 5 times in a minute, stop retrying
# — operator needs to see the logs rather than a busy-loop hiding them.
StartLimitIntervalSec=60
StartLimitBurst=5

[Install]
WantedBy=multi-user.target
UNIT

    echo ""
    echo -e "${DIM}Installing systemd unit to ${svc_file}...${NC}"
    if ! sudo install -m 0644 "$tmp_unit" "$svc_file"; then
        rm -f "$tmp_unit"
        echo -e "  ${RED}Failed to install unit file. Skipping auto-start.${NC}"
        return 1
    fi
    rm -f "$tmp_unit"

    sudo systemctl daemon-reload
    if sudo systemctl enable "$svc_name" >/dev/null 2>&1; then
        echo -e "  ${GREEN}Service enabled — will start on boot.${NC}"
        echo -e "  ${DIM}Start now:  ${CYAN}sudo systemctl start ${svc_name}${NC}"
        echo -e "  ${DIM}View logs:  ${CYAN}journalctl -u ${svc_name} -f${NC}"
        echo -e "  ${DIM}Disable:    ${CYAN}sudo systemctl disable ${svc_name}${NC}"
    else
        echo -e "  ${YELLOW}Unit installed but enable failed. Check: systemctl status ${svc_name}${NC}"
    fi
}

if [ "$PLATFORM" = "linux" ] && check_cmd systemctl && [ -d /etc/systemd/system ]; then
    # Skip if we can't prompt (piped, no tty) — never surprise-enable a
    # system service in an unattended install.
    if [ -t 1 ] && [ -r /dev/tty ]; then
        # Skip if an existing unit is already installed — don't clobber
        # a deliberate customisation.
        if [ ! -f /etc/systemd/system/opensentry-cloudnode.service ]; then
            echo ""
            echo -e "${BOLD}  Auto-start on boot?${NC}"
            echo -e "  ${DIM}Installs a systemd service that starts CloudNode when your system boots.${NC}"
            echo -e "  ${DIM}Useful for headless deployments like Raspberry Pi.${NC}"
            reply=""
            printf "  Install systemd service? [y/N]: "
            read -r reply </dev/tty || reply="n"
            case "${reply}" in
                y|Y|yes|YES)
                    install_systemd_service
                    ;;
            esac
        fi
    fi
fi

# ── Add to PATH hint ──────────────────────────────────────────────
IN_PATH=false
case ":$PATH:" in
    *":$INSTALL_DIR:"*) IN_PATH=true ;;
esac

# ── Done ──────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}  CloudNode installed successfully.${NC}"
echo ""
echo -e "  ${BOLD}Next steps:${NC}"
echo ""
echo -e "  1. Run setup:        ${CYAN}${INSTALL_DIR}/opensentry-cloudnode setup${NC}"
echo -e "  2. Start streaming:  ${CYAN}${INSTALL_DIR}/opensentry-cloudnode${NC}"
echo ""

if [ "$IN_PATH" = false ]; then
    echo -e "  ${DIM}Tip: Add to PATH for easier access:${NC}"
    if [ "$PLATFORM" = "macos" ]; then
        echo -e "  ${CYAN}echo 'export PATH=\"\$HOME/.opensentry:\$PATH\"' >> ~/.zshrc${NC}"
    else
        echo -e "  ${CYAN}echo 'export PATH=\"\$HOME/.opensentry:\$PATH\"' >> ~/.bashrc${NC}"
    fi
    echo ""
fi

echo -e "  ${DIM}Get your API key at ${CYAN}https://opensentry-command.fly.dev${NC}"
echo ""
