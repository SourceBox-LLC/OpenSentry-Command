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

# ── Shared prompt helper ───────────────────────────────────────────
# The installer is usually run via `curl | bash`, so stdin is the pipe
# from curl, not a terminal.  Reading from /dev/tty is how we still get
# an interactive yes/no from the operator — skip silently if the
# controlling terminal isn't available (CI, container build, etc.).
#
# Default answer is "yes" for every prompt the installer asks.
# Operators running this one-liner almost always want the thing we're
# about to install; making them type `y` for each step is friction
# without safety, and they can still decline.
prompt_yes() {
    local prompt_msg="$1"
    if [ ! -t 1 ] || [ ! -r /dev/tty ]; then
        # No tty — assume yes so unattended installs (cloud-init,
        # Ansible, curl | bash in Dockerfile builds) still work.
        return 0
    fi
    local reply=""
    printf "  %b " "${prompt_msg} [Y/n]:"
    read -r reply </dev/tty || reply="n"
    case "${reply:-y}" in
        y|Y|yes|YES) return 0 ;;
        *) return 1 ;;
    esac
}

# Install one or more apt packages after asking the operator.  Returns 0
# on success (or if declined), 1 on actual apt failure so callers can
# decide whether to continue or bail.  Silently no-ops on non-apt
# systems — we'd rather print a manual-install hint than try to detect
# dnf/pacman/apk and get it wrong.
apt_install_pkgs() {
    local prompt_msg="$1"
    shift
    local pkgs="$*"
    if ! check_cmd apt-get; then
        echo -e "  ${DIM}Install manually: ${CYAN}sudo apt install ${pkgs}${NC}"
        return 1
    fi
    if ! prompt_yes "${prompt_msg}"; then
        echo -e "  ${DIM}Skipped — install manually: ${CYAN}sudo apt install ${pkgs}${NC}"
        return 1
    fi
    echo -e "  ${DIM}Running: sudo apt-get install -y ${pkgs}${NC}"
    # Run `apt-get update` opportunistically — a stale cache is the #1
    # cause of "E: Unable to locate package" errors on fresh Pi images.
    # Quiet flag keeps the output from drowning out the installer banner.
    if sudo apt-get update -qq && sudo apt-get install -y $pkgs; then
        return 0
    else
        echo -e "  ${RED}apt install failed for: ${pkgs}${NC}"
        return 1
    fi
}

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
#
# Pi users (aarch64 / armv7) always hit this path until we publish
# ARM binaries in the release matrix — so this needs to be a real
# "install everything for you" flow, not a "here's what to type" wall
# of text.  We auto-install the whole build toolchain via apt and
# bootstrap rustup non-interactively; the operator just presses Enter.
if [ -z "$DOWNLOAD_URL" ]; then
    echo -e "${YELLOW}No pre-built binary available. Building from source...${NC}"
    echo ""

    # ── Build toolchain (gcc / make / pkg-config / libbz2) ─────────
    # On Debian/Ubuntu/Raspberry Pi OS, `build-essential` pulls in
    # gcc/g++/make.  pkg-config and libbz2-dev are needed by transitive
    # crates (ring, bzip2-sys) — missing libbz2-dev is the most common
    # source-build failure on a fresh Pi image, so we install it up
    # front rather than waiting for cargo to fail mid-compile.
    if [ "$PLATFORM" = "linux" ] && check_cmd apt-get; then
        NEED_APT=""
        check_cmd gcc         || NEED_APT="$NEED_APT build-essential"
        check_cmd make        || NEED_APT="$NEED_APT build-essential"
        check_cmd git         || NEED_APT="$NEED_APT git"
        check_cmd pkg-config  || NEED_APT="$NEED_APT pkg-config"
        # libbz2-dev is a header-only check — no CLI to probe for — so
        # we install it unconditionally when already calling apt.  It's
        # ~90 KB and pulled in transitively by the `zip` crate's
        # `bzip2-sys`; skipping it is the most common source-build
        # failure on a fresh Pi image, 15 minutes deep into cargo.
        # (We don't need libssl-dev — CloudNode uses rustls, not OpenSSL.)
        NEED_APT="$NEED_APT libbz2-dev"
        # De-dup (build-essential may appear twice).
        NEED_APT=$(echo "$NEED_APT" | tr ' ' '\n' | awk 'NF && !seen[$0]++' | tr '\n' ' ')
        if [ -n "$(echo "$NEED_APT" | tr -d ' ')" ]; then
            echo -e "  ${DIM}Build toolchain needed: ${CYAN}${NEED_APT}${NC}"
            if ! apt_install_pkgs "Install build toolchain via apt?" $NEED_APT; then
                echo -e "${RED}Cannot build from source without these packages.${NC}"
                exit 1
            fi
        fi
    elif ! check_cmd git; then
        echo -e "${RED}git is required but not installed.${NC}"
        if [ "$PLATFORM" = "macos" ]; then
            echo -e "Install: ${CYAN}xcode-select --install${NC}"
        fi
        exit 1
    fi

    # ── Rust toolchain via rustup ──────────────────────────────────
    # If cargo is already on PATH we use whatever version the user has;
    # otherwise we install stable via the official rustup one-liner
    # (non-interactive with -y).  After install we source cargo's env
    # script so `cargo` resolves in *this* shell invocation — without
    # that the very next `cargo build` call would fail with "command
    # not found" even though rustup landed successfully.
    if ! check_cmd cargo; then
        echo ""
        echo -e "  ${BOLD}Rust toolchain not found.${NC}"
        echo -e "  ${DIM}CloudNode needs rustc + cargo to build from source.${NC}"
        if prompt_yes "Install Rust via rustup (the official installer)?"; then
            echo -e "  ${DIM}Running rustup-init -y (stable toolchain, default profile)...${NC}"
            # --default-toolchain stable: pin to stable to avoid nightly
            # surprises. --profile minimal: skip docs/clippy/rust-src we
            # don't need for a release build — saves ~300 MB on a Pi.
            if curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | \
                 sh -s -- -y --default-toolchain stable --profile minimal; then
                # shellcheck disable=SC1091
                . "$HOME/.cargo/env"
                echo -e "  Rust:      ${GREEN}$(rustc --version 2>&1 | awk '{print $2}') (installed)${NC}"
            else
                echo -e "${RED}rustup install failed. Re-run after installing manually.${NC}"
                exit 1
            fi
        else
            echo -e "${RED}Cannot build from source without Rust.${NC}"
            echo -e "Install: ${CYAN}curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh${NC}"
            exit 1
        fi
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

    # Build time on a Pi 4 is ~10-15 min — the `quiet` flag hides
    # cargo's per-crate progress but we print a heads-up so operators
    # don't think the terminal hung.
    echo -e "${DIM}Building (~10-15 min on Raspberry Pi 4)...${NC}"
    (cd "$CLONE_DIR" && cargo build --release --quiet)

    cp "$CLONE_DIR/target/release/opensentry-cloudnode" "$INSTALL_DIR/opensentry-cloudnode"
    chmod +x "$INSTALL_DIR/opensentry-cloudnode"

    echo -e "${GREEN}Build complete.${NC}"
fi

# ── Check for ffmpeg + v4l-utils ──────────────────────────────────
# ffmpeg is the encoder; v4l-utils gives operators `v4l2-ctl` for
# diagnosing "camera not detected" issues — tiny package, huge help
# in support threads, so we install it alongside rather than asking.
echo ""
if check_cmd ffmpeg; then
    FFMPEG_VERSION=$(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')
    echo -e "  ffmpeg:    ${GREEN}${FFMPEG_VERSION} (installed)${NC}"
    # ffmpeg is present but v4l-utils might not be.  Quiet install if
    # we're on a Linux box with apt — no prompt, it's tiny and useful.
    if [ "$PLATFORM" = "linux" ] && ! check_cmd v4l2-ctl && check_cmd apt-get; then
        echo -e "  ${DIM}Installing v4l-utils for camera diagnostics...${NC}"
        sudo apt-get install -y v4l-utils >/dev/null 2>&1 || true
    fi
else
    echo -e "  ffmpeg:    ${YELLOW}not found${NC}"
    echo ""
    echo -e "${YELLOW}CloudNode requires ffmpeg for video processing.${NC}"

    if [ "$PLATFORM" = "linux" ]; then
        # apt is the common case (Debian/Ubuntu/Raspberry Pi OS).  Ship
        # v4l-utils in the same apt invocation so we only prompt once.
        # Other distros (dnf/pacman/apk) get a manual-install hint —
        # auto-detecting every package manager is more footgun than win.
        if apt_install_pkgs "Install ffmpeg + v4l-utils via apt?" ffmpeg v4l-utils; then
            echo -e "  ffmpeg:    ${GREEN}installed${NC}"
        fi
    elif [ "$PLATFORM" = "macos" ]; then
        if check_cmd brew; then
            if prompt_yes "Install ffmpeg now with Homebrew?"; then
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

# ── Raspberry Pi–specific checks ──────────────────────────────────
# On a Pi the operator hits two common gotchas:
#   1. Their user isn't in the `video` group, so opening /dev/video0
#      fails with EACCES and the setup wizard silently shows zero
#      cameras detected.
#   2. `/dev/video10` (the V4L2 M2M hardware H.264 encoder) isn't
#      present, so FFmpeg's hw-encoder probe falls back to libx264.
#      On a Pi 4 that means two 720p30 streams can pin the CPU and
#      thermal-throttle into a pipeline wedge.  The supervisor now
#      auto-recovers from the wedge, but avoiding it entirely is still
#      the win.
# Both checks run only on Linux + ARM — no point nagging an x86 NUC.
if [ "$PLATFORM" = "linux" ] && { [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "armv7" ]; }; then
    IS_PI=false
    if [ -r /proc/device-tree/model ] && grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null; then
        IS_PI=true
    fi

    # `video` group membership — required to open USB webcams without
    # systemd's SupplementaryGroups rewrite.
    CURRENT_USER="${SUDO_USER:-$USER}"
    if ! id -nG "$CURRENT_USER" 2>/dev/null | tr ' ' '\n' | grep -qx video; then
        echo ""
        echo -e "  ${BOLD}User ${CURRENT_USER} is not in the 'video' group.${NC}"
        echo -e "  ${DIM}USB cameras live at /dev/video* and need this group for access.${NC}"
        if prompt_yes "Add ${CURRENT_USER} to the video group?"; then
            if sudo usermod -a -G video "$CURRENT_USER"; then
                echo -e "  ${GREEN}Added to video group.${NC}  ${DIM}Log out + back in for it to take effect${NC}"
                echo -e "  ${DIM}(or just reboot — the systemd service works without this).${NC}"
            else
                echo -e "  ${RED}usermod failed — add manually: ${CYAN}sudo usermod -a -G video ${CURRENT_USER}${NC}"
            fi
        fi
    fi

    # Hardware encoder device.  Only warn on Pi specifically — other
    # ARM SBCs (Jetson, Rock Pi, etc.) have different encoder paths
    # and our probe picks them up elsewhere.
    if [ "$IS_PI" = true ] && [ ! -e /dev/video10 ]; then
        echo ""
        echo -e "  ${YELLOW}Pi detected but /dev/video10 is missing.${NC}"
        echo -e "  ${DIM}That device is the V4L2 M2M hardware H.264 encoder. Without${NC}"
        echo -e "  ${DIM}it, FFmpeg falls back to software libx264 — fine for one${NC}"
        echo -e "  ${DIM}camera, but two 720p30 streams will thermal-throttle a Pi 4.${NC}"
        echo -e "  ${DIM}To enable: ensure ${CYAN}bcm2835-codec${NC}${DIM} kernel module is loaded${NC}"
        echo -e "  ${DIM}(default on Pi OS; may be missing on minimal / Ubuntu Server images).${NC}"
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
