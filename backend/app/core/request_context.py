"""
Per-request context (request_id + org_id) backed by Python contextvars.

Why this exists:
  - When a customer says "I got a 500 at 3:14pm," we currently can't
    trace their specific request through logs.  A request_id assigned
    in middleware + included in every log line + returned to the
    client as ``X-Request-Id`` makes that lookup trivial.
  - When debugging "this notification didn't go out for org X," we
    don't want to grep the logs for the kind name and hope every
    matching line is the right org.  Stamping ``org_id`` on every
    log record (via ``app/core/logging_setup.py``) means a single
    grep on the org_id surfaces the full request flow.

Why contextvars:
  - Each FastAPI request runs in its own asyncio task.  contextvars
    are task-scoped — setting a value in one request never leaks to
    another, even without explicit reset.
  - Background loops (motion digest, email worker) run outside any
    request task; they get the empty-string default, which the
    logging filter renders as ``"-"`` so the log line stays aligned.
  - Code paths between middleware and endpoint, between auth dep
    and route handler, etc. all see the same value via implicit
    propagation — no need to thread the request object everywhere.
"""

from __future__ import annotations

import contextvars
import uuid

# ── Module-level contextvars ────────────────────────────────────────
# Defaults are empty strings so consumers can do ``if get_request_id():``
# without an extra ``is None`` check.  The logging filter normalises
# empty → "-" for human-readable output.

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default=""
)
_org_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "org_id", default=""
)


# ── Public API ──────────────────────────────────────────────────────


def get_request_id() -> str:
    """Return the current request id, or empty string if unset."""
    return _request_id.get()


def set_request_id(value: str) -> contextvars.Token:
    """Set the current request id.  Returns a token the caller can
    pass to ``reset_request_id`` to undo the set in a ``finally``
    block.  The reset isn't strictly required for FastAPI requests
    (each request is a new asyncio task with its own contextvar copy)
    but is good defensive practice for code paths that might run in a
    shared task — e.g. test suites that drive the middleware
    directly."""
    return _request_id.set(value)


def reset_request_id(token: contextvars.Token) -> None:
    _request_id.reset(token)


def get_org_id() -> str:
    """Return the current org id, or empty string if unauthenticated."""
    return _org_id.get()


def set_org_id(value: str) -> contextvars.Token:
    return _org_id.set(value)


def reset_org_id(token: contextvars.Token) -> None:
    _org_id.reset(token)


def new_request_id() -> str:
    """Mint a fresh short-form request id.

    16 hex chars from a uuid4 — short enough for a customer to read
    aloud over a support call, long enough to be globally unique in
    any log window we'd ever search.  Avoids the dashed full-uuid
    form because dashes break some text-based log greppers.
    """
    return uuid.uuid4().hex[:16]
