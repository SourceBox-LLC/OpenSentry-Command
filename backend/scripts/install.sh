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

REPO="SourceBox-LLC/OpenSentry-CloudNode"
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
    RELEASE_TAG=$(echo "$RELEASE_JSON" | grep '"tag_name"' | head -1 | sed 's/.*"tag_name": *"//;s/".*//')

    # Look for matching binary in release assets
    ASSET_PATTERN="${PLATFORM}.*${ARCH}"
    DOWNLOAD_URL=$(echo "$RELEASE_JSON" | grep -o '"browser_download_url": "[^"]*'"${ASSET_PATTERN}"'[^"]*"' | head -1 | sed 's/"browser_download_url": "//;s/"$//')
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
    if [ "$PLATFORM" = "linux" ]; then
        echo -e "  Install:  ${CYAN}sudo apt install ffmpeg${NC}"
    elif [ "$PLATFORM" = "macos" ]; then
        echo -e "  Install:  ${CYAN}brew install ffmpeg${NC}"
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
