"""
Install script routes for CloudNode.

Serves platform-specific install scripts so users can install with:
  Linux/macOS:  curl -fsSL https://opensentry-command.fly.dev/install.sh | bash
  Windows:      irm https://opensentry-command.fly.dev/install.ps1 | iex
"""

from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["installation"])

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"


def _read_script(filename: str) -> str:
    """Read an install script from the scripts directory."""
    script_path = SCRIPTS_DIR / filename
    return script_path.read_text(encoding="utf-8")


@router.get("/install.sh", response_class=PlainTextResponse)
async def install_sh():
    """Serve the bash install script for Linux/macOS."""
    content = _read_script("install.sh")
    return PlainTextResponse(
        content=content,
        media_type="text/x-shellscript",
        headers={"Content-Disposition": "inline; filename=install.sh"},
    )


@router.get("/install.ps1", response_class=PlainTextResponse)
async def install_ps1():
    """Serve the PowerShell install script for Windows."""
    content = _read_script("install.ps1")
    return PlainTextResponse(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": "inline; filename=install.ps1"},
    )
