"""
Signed unsubscribe tokens for email footers.

Each email's footer includes an unsubscribe link of the form

    ``{frontend}/api/notifications/email/unsubscribe?t=<jwt>``

The token carries (org_id, kind, issued_at) signed with a server
secret so anyone clicking the link doesn't have to be authenticated
to disable that alert type for their org.

Why JWT and not a database token table:
  - Tokens are issued at email-send time and consumed at click time;
    rate of issuance dwarfs rate of consumption (every send vs. one
    click).  Persisting them would mean a write per send for an
    artifact almost no one ever touches.
  - JWT signed-with-secret achieves the same security as DB-token
    lookup at zero storage cost.  Forging a token requires the secret;
    rotating the secret invalidates every outstanding link, which is
    the right behaviour after a key compromise.

Why no expiry:
  - The link's whole purpose is "let the user opt out forever."  An
    expired link defeats the point — they'd click it from a 6-month-old
    email and be told "this link has expired, please log in to manage
    settings" which is exactly the friction the link was supposed to
    avoid.  CAN-SPAM also requires the link to remain functional for
    at least 30 days; we just go forever.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import jwt

from app.core.config import settings

logger = logging.getLogger(__name__)


_JWT_ALGORITHM = "HS256"


def _get_secret() -> str:
    """Return the secret used to sign unsubscribe tokens.

    Derived from CLERK_SECRET_KEY (always present in any deployed
    instance).  Falling back to a hardcoded test sentinel keeps unit
    tests working without the operator having to set yet another
    secret.  In production the CLERK_SECRET_KEY is never empty so
    the fallback is unreachable.
    """
    return settings.CLERK_SECRET_KEY or "test-secret-not-for-production"


def make_token(org_id: str, kind: str) -> str:
    """Sign an unsubscribe JWT for ``(org_id, kind)``.

    Issued-at claim included so an audit can later distinguish "this
    token was issued before the secret rotation" from "this token is
    forged."  Subject claim doubles as a static identifier so external
    log scanners can spot unsubscribe attempts.
    """
    payload = {
        "org_id": org_id,
        "kind": kind,
        "iat": int(time.time()),
        "sub": "email-unsubscribe",
    }
    return jwt.encode(payload, _get_secret(), algorithm=_JWT_ALGORITHM)


def verify_token(token: str) -> Optional[tuple[str, str]]:
    """Decode + verify an unsubscribe token.

    Returns ``(org_id, kind)`` on success, ``None`` on any failure
    (bad signature, malformed, missing claims).  Failure is logged at
    INFO so a stream of bad tokens is visible without hitting WARN
    noise floors — most likely cause of a real bad token in
    production is an old email after a secret rotation, not an attack.
    """
    if not token or not isinstance(token, str):
        return None
    try:
        claims = jwt.decode(
            token,
            _get_secret(),
            algorithms=[_JWT_ALGORITHM],
            options={"require": ["org_id", "kind", "sub"]},
        )
    except jwt.InvalidTokenError as exc:
        logger.info("[Unsubscribe] token verify failed: %s", type(exc).__name__)
        return None

    if claims.get("sub") != "email-unsubscribe":
        # Wrong subject — refuse even with a valid signature.  Defends
        # against future tokens with the same key being misused.
        logger.info("[Unsubscribe] token sub mismatch")
        return None

    org_id = claims.get("org_id")
    kind = claims.get("kind")
    if not org_id or not kind:
        return None
    return (org_id, kind)


def build_unsubscribe_url(org_id: str, kind: str) -> str:
    """Construct the full clickable URL for the email footer."""
    token = make_token(org_id, kind)
    base = (settings.FRONTEND_URL or "").rstrip("/")
    return f"{base}/api/notifications/email/unsubscribe?t={token}"
