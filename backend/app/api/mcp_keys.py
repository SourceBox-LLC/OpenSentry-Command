"""
MCP API Key management endpoints.
Users generate keys on the /mcp page; keys are stored hashed (SHA-256).
"""

import hashlib
import secrets
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import AuthUser, require_admin, require_active_billing
from app.core.database import get_db
from app.mcp.activity import McpEvent, tracker
from app.models.models import McpApiKey

router = APIRouter(prefix="/api/mcp", tags=["mcp"])

KEY_PREFIX = "osc_"


def _generate_key() -> str:
    """Generate a random MCP API key: osc_ + 32 hex chars."""
    return KEY_PREFIX + secrets.token_hex(16)


def _log_key_event(
    org_id: str, tool_name: str, key_name: str, user: AuthUser
):
    """Log a key management event to the MCP activity tracker."""
    admin_label = user.email or user.username or user.user_id[:12]
    tracker.log_event(McpEvent(
        id=str(uuid.uuid4()),
        timestamp=time.time(),
        tool_name=tool_name,
        org_id=org_id,
        key_name=key_name,
        status="completed",
        duration_ms=None,
        args_summary=f"by {admin_label}",
    ))


@router.post("/keys")
async def create_mcp_key(
    name: str = "Default",
    user: AuthUser = Depends(require_active_billing),
    db: Session = Depends(get_db),
):
    """Generate a new MCP API key for the organization."""
    raw_key = _generate_key()
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    mcp_key = McpApiKey(
        org_id=user.org_id,
        key_hash=key_hash,
        name=name,
    )
    db.add(mcp_key)
    db.commit()
    db.refresh(mcp_key)

    _log_key_event(user.org_id, "key_created", name, user)

    return {
        "id": mcp_key.id,
        "name": mcp_key.name,
        "key": raw_key,  # Only returned once — never stored in plaintext
        "created_at": mcp_key.created_at.isoformat(),
        "warning": "Save this key now. You won't be able to see it again.",
    }


@router.get("/keys")
async def list_mcp_keys(
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """List all MCP API keys for the organization (without the actual key values)."""
    keys = (
        db.query(McpApiKey)
        .filter_by(org_id=user.org_id, revoked=False)
        .order_by(McpApiKey.created_at.desc())
        .all()
    )
    return [k.to_dict() for k in keys]


@router.delete("/keys/{key_id}")
async def revoke_mcp_key(
    key_id: int,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Revoke an MCP API key."""
    mcp_key = (
        db.query(McpApiKey)
        .filter_by(id=key_id, org_id=user.org_id)
        .first()
    )
    if not mcp_key:
        raise HTTPException(status_code=404, detail="Key not found")

    mcp_key.revoked = True
    db.commit()

    _log_key_event(user.org_id, "key_revoked", mcp_key.name, user)

    return {"success": True, "revoked": key_id}
