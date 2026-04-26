"""Standardized error envelope for the REST surface (`/api/*` routes).

Background
----------
``raise HTTPException(detail="some string")`` was the original pattern across
the codebase, and the frontend parser in ``services/api.js`` evolved around
it.  When a few routes started returning structured detail dicts (notably the
402 plan-limit-hit body in ``app.api.hls.push_segment``), ``new Error(detail)``
on the frontend produced ``"[object Object]"`` for any consumer that hadn't
been written to specifically pull a ``message`` field out.

Rather than mass-migrate every existing ``HTTPException`` site at once, this
module adds:

  - ``ApiError`` — drop-in replacement that produces a structured envelope.
    Use it on new endpoints, and migrate old ones opportunistically when you
    touch them.
  - The frontend's ``services/api.js`` knows about all three current shapes
    (``string``, ``dict``, Pydantic-422 ``list[dict]``) so it never falls
    through to the ``[object Object]`` path regardless of which backend
    pattern produced the response.

MCP coexistence
---------------
``ApiError`` is for FastAPI REST handlers only.  MCP tools at ``POST /mcp``
must keep raising ``fastmcp.exceptions.ToolError`` — the JSON-RPC error
envelope is fixed by the MCP protocol and is what every MCP client (Claude,
Cursor, custom agents) is built to consume.  ``app.mount("/mcp", mcp_app)``
mounts FastMCP as an ASGI sub-app, so exception handlers registered on the
parent FastAPI app don't reach into the MCP layer either way — the surfaces
are isolated by construction, this docstring just records the design.

Do NOT call ``raise ApiError`` inside helpers shared between REST handlers
and MCP tool implementations.  If you have to share business logic, either
return a result object that each side translates, or raise a plain Python
exception that each side catches and re-wraps.  See
``backend/app/mcp/server.py`` lines 503/532/572/595/etc. for the existing
``ToolError`` translation pattern.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


class ApiError(HTTPException):
    """Structured error response for the REST surface.

    Parameters
    ----------
    status_code : int
        HTTP status code.  4xx for client errors, 5xx for server.
    code : str
        Machine-readable error code (snake_case).  Frontend consumers can
        branch on ``e.code === "plan_limit_hit"`` etc. instead of regex-
        matching the message text.
    message : str
        Human-readable sentence the frontend can show to the user as-is.
        Should be operator-friendly, not a stack-trace fragment.
    **extra
        Optional structured fields to embed in the envelope.  Stay flat and
        JSON-serializable; the frontend reads them off ``e.detail.<key>``.

    Wire format
    -----------
    ::

        {
          "detail": {
            "error": "<code>",
            "message": "<message>",
            "<extra-key>": "<extra-value>",
            ...
          }
        }

    The flat shape mirrors the existing 402 plan-limit-hit body, so
    ``services/api.js``'s parser handles both old call sites and new
    ``ApiError`` ones identically.

    Examples
    --------
    Simple not-found::

        raise ApiError(404, "camera_not_found", "Camera not found")

    With structured fields::

        raise ApiError(
            402,
            "plan_limit_hit",
            f"Camera over the {plan} plan limit",
            plan=plan,
            max_cameras=max_cams,
            camera_name=camera.name,
        )
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        **extra: Any,
    ) -> None:
        detail: dict[str, Any] = {"error": code, "message": message}
        # Flatten extras into the envelope rather than nesting them.  Matches
        # the existing 402 shape so the frontend doesn't need a special case.
        for key, value in extra.items():
            if key in ("error", "message"):
                # These are reserved by the envelope itself.  Refuse silently
                # rather than overwriting — easier to spot in tests than a
                # confusing message swap at runtime.
                raise ValueError(
                    f"ApiError extra key {key!r} collides with reserved "
                    f"envelope field; rename the kwarg",
                )
            detail[key] = value
        super().__init__(status_code=status_code, detail=detail)
