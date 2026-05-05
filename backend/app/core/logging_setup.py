"""
Logging configuration that injects per-request context (request_id +
org_id) into every log line.

Usage: call ``configure_logging()`` once at application startup
(``main.py`` does this before any logger.info() can fire).  All
subsequent ``logging.getLogger(__name__).info(...)`` calls anywhere
in the codebase pick up the current contextvars from
``app/core/request_context.py``.

Format produced::

    2026-05-05T12:34:56 [INFO] [req=a1b2c3d4e5f6 org=org_xxx] app.api.notifications: created notif id=42

For lines outside any request context (background loops, startup,
tests calling code directly), request_id and org_id render as "-"
so the format stays aligned and grep-friendly.
"""

from __future__ import annotations

import logging
import sys

from app.core.request_context import get_org_id, get_request_id


class ContextFilter(logging.Filter):
    """Inject request_id + org_id from contextvars onto every record.

    Filters that return True let the record through; we always do —
    the work happens via the side-effect of writing the attributes.
    Putting this on a handler (rather than a logger) means it applies
    even when child loggers don't propagate.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        record.org_id = get_org_id() or "-"
        return True


_LOG_FORMAT = (
    "%(asctime)s [%(levelname)s] [req=%(request_id)s org=%(org_id)s] "
    "%(name)s: %(message)s"
)
_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

# Idempotency guard — configure_logging is called from main.py module
# load, but a test that imports main multiple times shouldn't double-
# install the handler.
_configured = False


def configure_logging(level: int = logging.INFO) -> None:
    """Install the context filter + format on the root logger.

    Idempotent.  Replaces any existing root logger handlers with a
    single stderr handler that uses our context-aware format string.
    Uvicorn manages its own named loggers (``uvicorn.access`` etc.)
    with their own handlers — those are intentionally left alone so
    the colorized access log keeps working.  Application code uses
    ``logging.getLogger(__name__)`` which inherits from root and so
    picks up our format automatically.
    """
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    handler.addFilter(ContextFilter())

    root = logging.getLogger()
    # Drop existing root handlers so we don't double-emit the same
    # line in two formats.  Named loggers (uvicorn.*) keep their own
    # handlers and are unaffected.
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level)

    _configured = True


def reset_for_tests() -> None:
    """Test-only: clear the idempotency guard so configure_logging
    can be called fresh.  Production code never calls this."""
    global _configured
    _configured = False
