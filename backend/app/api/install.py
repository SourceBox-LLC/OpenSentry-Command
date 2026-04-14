"""
Install script routes for CloudNode and MCP client setup.

Serves platform-specific install scripts so users can install with:
  Linux/macOS:  curl -fsSL https://opensentry-command.fly.dev/install.sh | bash
  Windows:      irm https://opensentry-command.fly.dev/install.ps1 | iex

MCP client auto-setup:
  Linux/macOS:  curl -fsSL <origin>/mcp-setup.sh | bash -s -- <key> <url>
  Windows:      & ([scriptblock]::Create((irm <origin>/mcp-setup.ps1))) <key> <url>

  NOTE: ``irm ... | iex -Args ...`` does NOT work — Invoke-Expression has no
  ``-Args`` parameter, so the arguments never reach the script's param block.
  Use the scriptblock pattern above instead.

Rate limiting: every endpoint here is public and unauthenticated, so
they're bucketed by client IP (see ``tenant_aware_key``).  The limits
are generous enough for a human running the one-liner a few times
while troubleshooting but tight enough that a bot can't hammer the
disk.  A legitimate install hits each script exactly once.
"""

from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.core.limiter import limiter

router = APIRouter(tags=["installation"])

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"


def _read_script(filename: str) -> str:
    """Read an install script from the scripts directory."""
    script_path = SCRIPTS_DIR / filename
    return script_path.read_text(encoding="utf-8")


@router.get("/install.sh", response_class=PlainTextResponse)
@limiter.limit("30/minute")
async def install_sh(request: Request):
    """Serve the bash install script for Linux/macOS."""
    content = _read_script("install.sh")
    return PlainTextResponse(
        content=content,
        media_type="text/x-shellscript",
        headers={"Content-Disposition": "inline; filename=install.sh"},
    )


@router.get("/install.ps1", response_class=PlainTextResponse)
@limiter.limit("30/minute")
async def install_ps1(request: Request):
    """Serve the PowerShell install script for Windows."""
    content = _read_script("install.ps1")
    return PlainTextResponse(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": "inline; filename=install.ps1"},
    )


# ── MCP Client Setup Scripts ─────────────────────────

@router.get("/mcp-setup.sh", response_class=PlainTextResponse)
@limiter.limit("30/minute")
async def mcp_setup_sh(request: Request):
    """Serve the MCP client setup script for Linux/macOS."""
    content = _read_script("mcp-setup.sh")
    return PlainTextResponse(
        content=content,
        media_type="text/x-shellscript",
        headers={"Content-Disposition": "inline; filename=mcp-setup.sh"},
    )


@router.get("/mcp-setup.ps1", response_class=PlainTextResponse)
@limiter.limit("30/minute")
async def mcp_setup_ps1(request: Request):
    """Serve the MCP client setup script for Windows."""
    content = _read_script("mcp-setup.ps1")
    return PlainTextResponse(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": "inline; filename=mcp-setup.ps1"},
    )
