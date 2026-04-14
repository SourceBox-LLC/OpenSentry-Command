"""
Shared rate limiter.

Keys requests by tenant where possible so one loud tenant can't starve
the global bucket for everyone else:

  1. ``X-Node-API-Key`` header → ``node:<sha256-prefix>``
     — CloudNodes get their own bucket, scoped to the node.
  2. ``Authorization: Bearer <jwt>`` → ``org:<org_id>``
     — Authenticated end-user requests share a bucket per-org.  The JWT
       payload is base64-decoded WITHOUT verification; it's only used
       as a bucket selector.  Full verification still happens in
       ``get_current_user`` before the endpoint body runs.
  3. Fallback → remote IP — used for sign-in, webhooks, and other
     unauthenticated routes.

Decoding the JWT unverified is safe for rate-limiting because an
attacker who forges a token with a different ``org_id`` only moves
themselves into a different bucket — they can't escape limits
entirely, and real auth still rejects them.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)


def _extract_org_from_jwt(token: str) -> str | None:
    """Pull ``org_id`` out of an unverified JWT payload. Returns None on
    anything unparseable — callers fall back to IP in that case."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        # Pad to a multiple of 4 so urlsafe_b64decode doesn't choke.
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload_b64))
        # V1 flat claim or V2 compact "o" claim.
        org_id = claims.get("org_id") or claims.get("o", {}).get("id")
        if isinstance(org_id, str) and org_id:
            return org_id
    except Exception:
        return None
    return None


def tenant_aware_key(request: Request) -> str:
    """Rate-limit bucket key for a request.  See module docstring."""
    # CloudNode requests — one bucket per node, identified by the hash
    # prefix of its API key (not the raw key — never log or bucket on that).
    node_key = request.headers.get("X-Node-API-Key")
    if node_key:
        digest = hashlib.sha256(node_key.encode()).hexdigest()[:16]
        return f"node:{digest}"

    # End-user requests — one bucket per org.
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        org_id = _extract_org_from_jwt(auth[7:])
        if org_id:
            return f"org:{org_id}"

    # Unauthenticated fallback.
    return get_remote_address(request)


# Shared rate limiter — per-tenant where possible, per-IP otherwise.
# Import this in any router module that needs rate limiting.
limiter = Limiter(key_func=tenant_aware_key)
