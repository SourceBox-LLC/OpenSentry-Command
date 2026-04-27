"""
Install script routes for CloudNode and MCP client setup.

CloudNode install:
  Linux/macOS:  curl -fsSL https://opensentry-command.fly.dev/install.sh | bash
  Windows:      MSI installer from the latest GitHub release. There is no
                PowerShell one-liner — the MSI is the supported Windows
                install path. See the CloudNode README for the download
                URL pattern.

MCP client auto-setup (separate from CloudNode install — these are for
configuring Claude / Cursor / etc. to talk to this Command Center):
  Linux/macOS:  curl -fsSL <origin>/mcp-setup.sh | bash -s -- <key> <url>
  Windows:      & ([scriptblock]::Create((irm <origin>/mcp-setup.ps1))) <key> <url>

  NOTE: ``irm ... | iex -Args ...`` does NOT work — Invoke-Expression has no
  ``-Args`` parameter, so the arguments never reach the script's param block.
  Use the scriptblock pattern above instead.

Direct binary downloads:
  ``GET /downloads/{os}/{arch}`` 302-redirects to the matching asset on the
  latest GitHub release of opensentry-cloud-node.  Gives us a stable
  vendor-controlled URL to publish in docs (no GitHub URL structure leaking
  into documentation) and a single place to later add caching/mirroring.

Rate limiting: every endpoint here is public and unauthenticated, so
they're bucketed by client IP (see ``tenant_aware_key``).  The limits
are generous enough for a human running the one-liner a few times
while troubleshooting but tight enough that a bot can't hammer the
disk.  A legitimate install hits each script exactly once.
"""

import re
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from app.core.limiter import limiter

router = APIRouter(tags=["installation"])

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"

# GitHub repo that hosts CloudNode release artifacts.  Must match the
# ``REPO`` constant in ``scripts/install.sh`` so both install paths
# agree on where binaries come from.
CLOUDNODE_GH_REPO = "SourceBox-LLC/opensentry-cloud-node"

# Allowed OS/arch combos for /downloads/{os}/{arch}.  Matches what
# install.sh already supports so users don't hit a friendlier URL and
# get a different answer than the one-liner would have given them.
_ALLOWED_OS = {"linux", "macos", "windows"}
_ALLOWED_ARCH = {"x86_64", "aarch64", "armv7"}

# Simple module-level cache for the GitHub "latest release" lookup.
# GitHub's unauthenticated API is 60/hour per IP, so we'd burn through
# that quickly on a busy install day without this.  10 minutes is short
# enough that a new release is reachable quickly and long enough to
# smooth out bursts.
_release_cache: dict[str, tuple[float, dict]] = {}
_RELEASE_CACHE_TTL_S = 600


async def _get_latest_release() -> dict | None:
    """Fetch (or cache-hit) the latest CloudNode release JSON from GitHub.

    Returns ``None`` if GitHub is unreachable or returned a non-2xx so
    callers can fall back gracefully.  We never raise from here because
    the install page should keep working even when GitHub has a bad day.
    """
    cached = _release_cache.get(CLOUDNODE_GH_REPO)
    if cached and (time.time() - cached[0]) < _RELEASE_CACHE_TTL_S:
        return cached[1]

    url = f"https://api.github.com/repos/{CLOUDNODE_GH_REPO}/releases/latest"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                url,
                headers={"Accept": "application/vnd.github+json"},
            )
        if resp.status_code != 200:
            return None
        data = resp.json()
        _release_cache[CLOUDNODE_GH_REPO] = (time.time(), data)
        return data
    except (httpx.HTTPError, ValueError):
        return None


def _pick_asset(release: dict, os_name: str, arch: str) -> str | None:
    """Find the release asset matching ``<os>.*<arch>`` in its filename.

    Mirrors the regex install.sh uses so both paths resolve to the same
    binary.  We prefer archives (.tar.gz/.zip) over raw binaries since
    GitHub Releases always bundles them that way.
    """
    assets = release.get("assets") or []
    pattern = re.compile(rf"{re.escape(os_name)}.*{re.escape(arch)}", re.IGNORECASE)

    # Preferred ordering: archives first, then raw binaries.
    def rank(name: str) -> int:
        lower = name.lower()
        if lower.endswith(".tar.gz") or lower.endswith(".tgz"):
            return 0
        if lower.endswith(".zip"):
            return 1
        return 2

    candidates = [a for a in assets if a.get("name") and pattern.search(a["name"])]
    if not candidates:
        return None

    candidates.sort(key=lambda a: rank(a["name"]))
    return candidates[0].get("browser_download_url") or None


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


# NOTE: The PowerShell CloudNode install one-liner (`/install.ps1`)
# was removed. Windows users install via the MSI from the latest
# GitHub release — that path supports Windows Service registration,
# Add/Remove Programs integration, and the upgrade/uninstall chain
# the PS one-liner couldn't do cleanly. See CloudNode README for the
# canonical download URL.
#
# The /mcp-setup.ps1 route below is unrelated — it configures MCP
# clients (Claude / Cursor / etc.) to talk to this Command Center,
# not to install CloudNode.


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


# ── Direct binary downloads ─────────────────────────

@router.get("/downloads/{os_name}/{arch}")
@limiter.limit("60/minute")
async def download_binary(request: Request, os_name: str, arch: str):
    """Redirect to the latest CloudNode binary for ``{os_name}/{arch}``.

    Returns ``302`` pointing at the matching asset on the latest GitHub
    release.  This gives docs/users a canonical vendor URL instead of
    leaking a GitHub URL structure that could drift if we ever move
    hosting providers.

    If GitHub is unreachable or the release lacks an asset for the
    requested combo, we 404 so clients fall back to the install
    script (which already has a source-build fallback baked in).
    """
    os_key = os_name.lower()
    arch_key = arch.lower()
    if os_key not in _ALLOWED_OS:
        raise HTTPException(
            status_code=404,
            detail=f"Unsupported OS '{os_name}'. Try one of: {sorted(_ALLOWED_OS)}.",
        )
    if arch_key not in _ALLOWED_ARCH:
        raise HTTPException(
            status_code=404,
            detail=f"Unsupported arch '{arch}'. Try one of: {sorted(_ALLOWED_ARCH)}.",
        )

    release = await _get_latest_release()
    if not release:
        raise HTTPException(
            status_code=503,
            detail="Release metadata unavailable. Try /install.sh on Linux/macOS, or download the MSI directly from the latest GitHub release on Windows.",
        )

    asset_url = _pick_asset(release, os_key, arch_key)
    if not asset_url:
        tag = release.get("tag_name", "latest")
        raise HTTPException(
            status_code=404,
            detail=f"No prebuilt binary for {os_key}/{arch_key} in release {tag}. Try the install script for a source fallback.",
        )

    return RedirectResponse(url=asset_url, status_code=302)
