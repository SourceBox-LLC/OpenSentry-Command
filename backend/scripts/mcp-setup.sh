#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────
# OpenSentry MCP Client Setup
# Automatically configure AI tools to connect to your
# OpenSentry cameras via the Model Context Protocol.
# ─────────────────────────────────────────────────────

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

API_KEY="${1:-}"
SERVER_URL="${2:-}"

if [[ -z "$API_KEY" || -z "$SERVER_URL" ]]; then
    echo -e "${RED}${BOLD}Error:${NC} Missing arguments"
    echo ""
    echo "Usage: bash mcp-setup.sh <api_key> <server_url>"
    echo ""
    echo "Get your command from the OpenSentry MCP dashboard:"
    echo "  https://opensentry-command.fly.dev/mcp"
    exit 1
fi

# ── Header ────────────────────────────────────────────

echo ""
echo -e "  ${GREEN}${BOLD}OpenSentry MCP Setup${NC}"
echo -e "  ${DIM}Configure AI tools to connect to your cameras${NC}"
echo ""

# ── Check for Python (needed for JSON manipulation) ───

PYTHON=""
if command -v python3 &>/dev/null; then
    PYTHON="python3"
elif command -v python &>/dev/null; then
    PYTHON="python"
else
    echo -e "${RED}Error: Python is required for JSON config editing.${NC}"
    echo "Install Python 3 and try again."
    exit 1
fi

# ── Detect MCP Clients ────────────────────────────────

# Client name, config path, detected (0=yes 1=no)
CLIENT_NAMES=()
CLIENT_CONFIGS=()
CLIENT_DETECTED=()

detect_client() {
    local name="$1"
    local config_path="$2"
    local detected=1

    # Check if config file or parent directory exists
    if [[ -f "$config_path" ]]; then
        detected=0
    elif [[ -d "$(dirname "$config_path")" ]]; then
        detected=0
    fi

    CLIENT_NAMES+=("$name")
    CLIENT_CONFIGS+=("$config_path")
    CLIENT_DETECTED+=("$detected")
}

# Claude Code
detect_client "Claude Code" "$HOME/.claude.json"

# Claude Desktop
if [[ "$(uname)" == "Darwin" ]]; then
    detect_client "Claude Desktop" "$HOME/Library/Application Support/Claude/claude_desktop_config.json"
else
    detect_client "Claude Desktop" "$HOME/.config/Claude/claude_desktop_config.json"
fi

# Cursor
detect_client "Cursor" "$HOME/.cursor/mcp.json"

# Windsurf
detect_client "Windsurf" "$HOME/.codeium/windsurf/mcp_config.json"

# ── Display Detected Clients ─────────────────────────

echo -e "  ${BOLD}MCP Clients:${NC}"
echo ""

DETECTED_COUNT=0
for i in "${!CLIENT_NAMES[@]}"; do
    if [[ "${CLIENT_DETECTED[$i]}" == "0" ]]; then
        echo -e "    ${GREEN}[$((i+1))]${NC} ${GREEN}●${NC} ${BOLD}${CLIENT_NAMES[$i]}${NC}"
        echo -e "        ${DIM}${CLIENT_CONFIGS[$i]}${NC}"
        ((DETECTED_COUNT++)) || true
    else
        echo -e "    ${DIM}[$((i+1))] ○ ${CLIENT_NAMES[$i]}${NC}"
        echo -e "        ${DIM}${CLIENT_CONFIGS[$i]} (not found)${NC}"
    fi
done

echo ""

if [[ "$DETECTED_COUNT" -eq 0 ]]; then
    echo -e "  ${YELLOW}No MCP clients detected.${NC}"
    echo -e "  ${DIM}You can still configure a client by entering its number.${NC}"
    echo ""
fi

# ── Prompt for Selection ──────────────────────────────

echo -e "  ${BOLD}Which clients would you like to configure?${NC}"
echo -e "  ${DIM}Enter numbers separated by commas (e.g. 1,3), 'all' for all detected, or 'q' to quit${NC}"
echo ""
# Read from the terminal, not stdin — stdin is the piped script when run via
# `curl ... | bash -s --`, so a plain `read` would immediately hit EOF.
if [[ -t 0 ]]; then
    read -rp "  > " SELECTION
else
    read -rp "  > " SELECTION </dev/tty
fi

if [[ "$SELECTION" == "q" || "$SELECTION" == "Q" ]]; then
    echo -e "\n  ${DIM}Setup cancelled.${NC}\n"
    exit 0
fi

# Parse selection
SELECTED=()
if [[ "$SELECTION" == "all" || "$SELECTION" == "ALL" ]]; then
    for i in "${!CLIENT_NAMES[@]}"; do
        if [[ "${CLIENT_DETECTED[$i]}" == "0" ]]; then
            SELECTED+=("$i")
        fi
    done
    if [[ ${#SELECTED[@]} -eq 0 ]]; then
        echo -e "\n  ${YELLOW}No detected clients to configure.${NC}\n"
        exit 0
    fi
else
    IFS=',' read -ra NUMS <<< "$SELECTION"
    for num in "${NUMS[@]}"; do
        num=$(echo "$num" | tr -d ' ')
        idx=$((num - 1))
        if [[ "$idx" -ge 0 && "$idx" -lt "${#CLIENT_NAMES[@]}" ]]; then
            SELECTED+=("$idx")
        else
            echo -e "  ${YELLOW}Skipping invalid selection: $num${NC}"
        fi
    done
fi

if [[ ${#SELECTED[@]} -eq 0 ]]; then
    echo -e "\n  ${YELLOW}No valid selections. Exiting.${NC}\n"
    exit 0
fi

echo ""

# ── Configure Selected Clients ────────────────────────

configure_client() {
    local name="$1"
    local config_path="$2"

    echo -e "  ${BLUE}Configuring ${BOLD}$name${NC}${BLUE}...${NC}"

    # Create parent directory if needed
    local dir
    dir="$(dirname "$config_path")"
    if [[ ! -d "$dir" ]]; then
        mkdir -p "$dir"
        echo -e "    ${DIM}Created directory: $dir${NC}"
    fi

    # Use Python to safely merge JSON
    $PYTHON - "$config_path" "$SERVER_URL" "$API_KEY" << 'PYEOF'
import json
import sys
import os

config_path = sys.argv[1]
server_url = sys.argv[2]
api_key = sys.argv[3]

# Read existing config
config = {}
if os.path.isfile(config_path):
    try:
        with open(config_path, "r") as f:
            content = f.read().strip()
            if content:
                config = json.loads(content)
    except (json.JSONDecodeError, IOError):
        # Back up corrupted file
        backup = config_path + ".bak"
        try:
            os.rename(config_path, backup)
            print(f"    Backed up existing config to {backup}")
        except IOError:
            pass
        config = {}

# Ensure mcpServers exists
if "mcpServers" not in config:
    config["mcpServers"] = {}

# Add/update OpenSentry entry
config["mcpServers"]["opensentry"] = {
    "type": "http",
    "url": server_url,
    "headers": {
        "Authorization": f"Bearer {api_key}"
    }
}

# Write back
with open(config_path, "w") as f:
    json.dump(config, f, indent=2)
    f.write("\n")

print("    OK")
PYEOF

    if [[ $? -eq 0 ]]; then
        echo -e "    ${GREEN}Done${NC} ${DIM}→ $config_path${NC}"
    else
        echo -e "    ${RED}Failed to configure $name${NC}"
    fi
    echo ""
}

for idx in "${SELECTED[@]}"; do
    configure_client "${CLIENT_NAMES[$idx]}" "${CLIENT_CONFIGS[$idx]}"
done

# ── Summary ───────────────────────────────────────────

echo -e "  ${GREEN}${BOLD}Setup Complete${NC}"
echo ""
echo -e "  ${DIM}Your AI tools can now access your OpenSentry cameras.${NC}"
echo -e "  ${DIM}Try asking: \"List my cameras\" or \"Show me what the front door sees\"${NC}"
echo ""
echo -e "  ${DIM}Manage your MCP keys at:${NC}"
echo -e "  ${CYAN}${SERVER_URL%/mcp}/mcp${NC}"
echo ""
