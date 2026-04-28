#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────
# SourceBox Sentry MCP Client Setup
# Automatically configure AI tools to connect to your
# SourceBox Sentry cameras via the Model Context Protocol.
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
    echo "Get your command from the SourceBox Sentry MCP dashboard:"
    echo "  https://opensentry-command.fly.dev/mcp"
    exit 1
fi

# ── Header ────────────────────────────────────────────

echo ""
echo -e "  ${GREEN}${BOLD}SourceBox Sentry MCP Setup${NC}"
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

# Tracks clients we refused to touch because they were running.
SKIPPED_CLIENTS=()

# Echoes the PID of a running matching process for the named client, or
# nothing if none. Refusing to write when the client is up avoids its own
# file-watcher stomping our write with stale in-memory state -- that's the
# bug the PS version of this script hit in the field.
# Tests can bypass by setting SOURCEBOX_SENTRY_MCP_ALLOW_RUNNING=1.
client_running_pid() {
    local name="$1"
    if [[ "${SOURCEBOX_SENTRY_MCP_ALLOW_RUNNING:-0}" == "1" ]]; then
        return 0
    fi
    local procs=""
    case "$name" in
        "Claude Code"|"Claude Desktop") procs="Claude claude" ;;
        "Cursor") procs="Cursor cursor" ;;
        "Windsurf") procs="Windsurf windsurf" ;;
        *) return 0 ;;
    esac
    for p in $procs; do
        local pid
        pid=$(pgrep -x "$p" 2>/dev/null | head -1 || true)
        if [[ -n "$pid" ]]; then
            echo "$pid"
            return 0
        fi
    done
}

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

# ── Warning: quit target apps ────────────────────────

echo -e "  ${YELLOW}${BOLD}Important:${NC}"
echo -e "  ${DIM}Quit Claude Code / Claude Desktop / Cursor / Windsurf before continuing.${NC}"
echo -e "  ${DIM}Running clients may overwrite config changes while the setup is writing.${NC}"
echo ""

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

    # Refuse to touch the config if the target client is currently running --
    # its own file-watcher will clobber our write with stale in-memory state.
    local running_pid
    running_pid=$(client_running_pid "$name")
    if [[ -n "$running_pid" ]]; then
        echo -e "    ${YELLOW}$name is currently running (pid $running_pid).${NC}"
        echo -e "    ${YELLOW}Skipping -- quit $name completely and re-run this script.${NC}"
        echo -e "    ${DIM}Your config was NOT modified.${NC}"
        echo ""
        SKIPPED_CLIENTS+=("$name")
        return
    fi

    # Create parent directory if needed
    local dir
    dir="$(dirname "$config_path")"
    if [[ ! -d "$dir" ]]; then
        mkdir -p "$dir"
        echo -e "    ${DIM}Created directory: $dir${NC}"
    fi

    # Use Python to safely merge JSON. Exit codes:
    #   0 = wrote config successfully
    #   2 = existing file unparseable — we refused to overwrite
    #   other = I/O or unexpected failure
    $PYTHON - "$config_path" "$SERVER_URL" "$API_KEY" << 'PYEOF'
import json
import shutil
import sys
import os

config_path = sys.argv[1]
server_url = sys.argv[2]
api_key = sys.argv[3]

# Read existing config. If the file exists and is non-empty but unparseable,
# ABORT instead of starting fresh — losing an existing .claude.json full of
# session state is catastrophic.
config = {}
if os.path.isfile(config_path):
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            config = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"    Could not parse {config_path} as JSON.", file=sys.stderr)
        print(f"    Error: {e}", file=sys.stderr)
        print("    Skipping this client to avoid overwriting your existing data.", file=sys.stderr)
        print("    Fix the file manually (or delete it) and re-run.", file=sys.stderr)
        sys.exit(2)
    except OSError as e:
        print(f"    Failed to read {config_path}: {e}", file=sys.stderr)
        sys.exit(3)

# Always back up the pre-existing config before we write anything.
if os.path.isfile(config_path):
    backup = config_path + ".bak"
    try:
        shutil.copy(config_path, backup)
        print(f"    Backed up existing config to {backup}")
    except OSError as e:
        print(f"    Warning: could not create backup at {backup}: {e}", file=sys.stderr)

# Ensure mcpServers exists (preserving any other entries already there).
if not isinstance(config.get("mcpServers"), dict):
    config["mcpServers"] = {}

# Add/update SourceBox Sentry entry.
config["mcpServers"]["opensentry"] = {
    "type": "http",
    "url": server_url,
    "headers": {
        "Authorization": f"Bearer {api_key}"
    }
}

# Write back atomically — write to a tempfile in the same dir, then rename.
# Avoids the "half-written config on crash" failure mode.
import tempfile
dir_ = os.path.dirname(config_path) or "."
fd, tmp = tempfile.mkstemp(prefix=".mcp-setup-", suffix=".json", dir=dir_)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
        f.write("\n")
    os.replace(tmp, config_path)
except Exception as e:
    try:
        os.unlink(tmp)
    except OSError:
        pass
    print(f"    Failed to write {config_path}: {e}", file=sys.stderr)
    sys.exit(4)

print("    OK")
PYEOF
    rc=$?

    if [[ $rc -eq 0 ]]; then
        echo -e "    ${GREEN}Done${NC} ${DIM}→ $config_path${NC}"
    elif [[ $rc -eq 2 ]]; then
        # Parse-failure abort message is already on stderr above — just note the skip.
        echo -e "    ${YELLOW}Skipped $name (existing config not valid JSON).${NC}"
    else
        echo -e "    ${RED}Failed to configure $name (exit $rc)${NC}"
    fi
    echo ""
}

for idx in "${SELECTED[@]}"; do
    configure_client "${CLIENT_NAMES[$idx]}" "${CLIENT_CONFIGS[$idx]}"
done

# ── Summary ───────────────────────────────────────────

if [[ ${#SKIPPED_CLIENTS[@]} -gt 0 ]]; then
    echo -e "  ${YELLOW}${BOLD}Skipped (still running):${NC}"
    for s in "${SKIPPED_CLIENTS[@]}"; do
        echo -e "    ${YELLOW}* $s${NC}"
    done
    echo ""
    echo -e "  ${DIM}Quit the above and re-run this script to configure them.${NC}"
    echo ""
fi

echo -e "  ${GREEN}${BOLD}Setup Complete${NC}"
echo ""
echo -e "  ${DIM}Your AI tools can now access your SourceBox Sentry cameras.${NC}"
echo -e "  ${DIM}Restart the clients you configured so they pick up the new MCP server.${NC}"
echo -e "  ${DIM}Try asking: \"List my cameras\" or \"Show me what the front door sees\"${NC}"
echo ""
echo -e "  ${DIM}Manage your MCP keys at:${NC}"
echo -e "  ${CYAN}${SERVER_URL%/mcp}/mcp${NC}"
echo ""
