"""
Email template rendering — Jinja2 over the templates in
``backend/app/templates/emails/``.

Each notification kind has three template files:

  ``<kind>.subject.txt.j2`` — the subject line (single line of text)
  ``<kind>.body.txt.j2``    — the plain-text body
  ``<kind>.body.html.j2``   — the per-kind body block (NOT a full
                              HTML doc — gets wrapped by _layout.html.j2)

The HTML body block is wrapped by the shared layout, which provides
the brand header, severity bar, and unsubscribe footer.  Plain-text
emails go through unchanged.

This module is the *only* place that knows about the template
filesystem layout.  Callers go through ``render(kind, notification,
unsubscribe_url)`` and get back a ``(subject, body_text, body_html)``
triple that's safe to hand straight to the Resend transport.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from app.core.config import settings

logger = logging.getLogger(__name__)


_TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "emails"


# Severity → hex.  Used for the colored bar at the top of the email
# layout so the visual urgency matches the inbox's severity badge.
_SEVERITY_COLORS = {
    "critical": "#ef4444",
    "error":    "#ef4444",
    "warning":  "#f59e0b",
    "info":     "#22c55e",
}


# Single Jinja2 environment, lazily initialised on first render.
# Autoescape is selected per-template by ``_should_autoescape`` —
# .html.j2 files get full HTML escaping, .txt.j2 files do not.
# select_autoescape's built-in extension matcher doesn't work for our
# layout because every file ends in .j2; the meaningful distinction
# is the inner extension (.html. vs .txt.).
_env: Optional[Environment] = None


def _should_autoescape(template_name: Optional[str]) -> bool:
    """True if Jinja should HTML-escape variable substitutions in
    this template.  Our convention: ``foo.body.html.j2`` is HTML
    (autoescape on); ``foo.body.txt.j2`` and ``foo.subject.txt.j2``
    are plain text (autoescape off, otherwise the text body would
    show ``&amp;`` and ``&lt;`` instead of the original characters).
    """
    if not template_name:
        return False
    return ".html." in template_name or template_name.endswith(".html")


def _get_env() -> Environment:
    global _env
    if _env is None:
        _env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            autoescape=_should_autoescape,
            # Strip leading/trailing whitespace lines around block tags
            # so the rendered email isn't littered with blank lines from
            # the {% if %} ... {% endif %} guards.
            trim_blocks=True,
            lstrip_blocks=True,
        )
    return _env


def _reset_env_for_tests() -> None:
    """Drop the cached environment.  Tests that change the templates
    directory or load order can call this between cases."""
    global _env
    _env = None


# ── Public API ───────────────────────────────────────────────────────

def render(
    kind: str,
    notification,
    *,
    unsubscribe_url: str,
    dashboard_url: Optional[str] = None,
) -> tuple[str, str, str]:
    """Render a notification into ``(subject, body_text, body_html)``.

    Returns a 3-tuple suitable for handing straight to the Resend
    transport.  Falls back to a generic template on missing files
    rather than crashing — a missing template should not silence the
    alert entirely (the inbox notification still happens; the email
    just gets a less-specific shape).

    Parameters
    ----------
    kind
        Notification kind (``"camera_offline"``, etc.) — drives template
        file lookup.
    notification
        ``app.models.models.Notification`` instance.  Templates access
        ``notification.title``, ``.body``, ``.severity``,
        ``.camera_id``, ``.node_id``, ``.link``, and ``.meta`` (parsed
        dict from the JSON column).
    unsubscribe_url
        Pre-signed URL for the footer's unsubscribe link.  Caller is
        responsible for signing — see ``app.core.email_unsubscribe``.
    dashboard_url
        Base URL for "view in dashboard" links.  Defaults to the
        configured FRONTEND_URL.
    """
    env = _get_env()
    dash = (dashboard_url or settings.FRONTEND_URL or "").rstrip("/")
    severity_color = _SEVERITY_COLORS.get(notification.severity, "#22c55e")

    # Notification has a JSON-blob ``meta_json`` field we want exposed
    # as a dict to templates.  Lazy-parse here so templates can write
    # ``notification.meta.incident_id`` naturally.
    notif_proxy = _NotificationProxy(notification)

    context = {
        "notification": notif_proxy,
        "unsubscribe_url": unsubscribe_url,
        "dashboard_url": dash,
        "severity_color": severity_color,
    }

    subject = _render_or_fallback(
        env, f"{kind}.subject.txt.j2", context,
        fallback=f"[SourceBox Sentry] {notif_proxy.title}",
    ).strip()
    body_text = _render_or_fallback(
        env, f"{kind}.body.txt.j2", context,
        fallback=_generic_body_text(notif_proxy, dash, unsubscribe_url),
    )
    body_html_inner = _render_or_fallback(
        env, f"{kind}.body.html.j2", context,
        fallback=_generic_body_html(notif_proxy),
    )

    # Wrap the per-kind HTML body in the shared layout.  Subject is
    # also passed in (escaped already by autoescape since it's coming
    # from the safe rendered string) for the <title> tag.
    layout_context = {
        **context,
        "subject_safe": subject,
        "body_html": body_html_inner,
    }
    body_html = _render_or_fallback(
        env, "_layout.html.j2", layout_context,
        # Bare-bones fallback if even the layout is missing — the
        # email still goes out, just without the brand wrap.
        fallback=body_html_inner,
    )

    return subject, body_text, body_html


# ── Internals ────────────────────────────────────────────────────────

class _NotificationProxy:
    """Read-only view over a Notification with a parsed ``meta`` dict.

    Templates would otherwise need to call ``json.loads()`` on
    ``meta_json`` themselves, which Jinja's sandboxed env can't do
    cleanly.  Wrapping here keeps the template syntax natural
    (``notification.meta.incident_id``) without giving templates
    access to the full SQLAlchemy model.
    """

    __slots__ = ("_n", "meta")

    def __init__(self, notification):
        self._n = notification
        self.meta = self._parse_meta(notification)

    def __getattr__(self, name):
        # Forward unknown attribute reads to the wrapped notification.
        return getattr(self._n, name)

    @staticmethod
    def _parse_meta(notification) -> dict:
        raw = getattr(notification, "meta_json", None)
        if not raw:
            return {}
        try:
            import json as _json
            data = _json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (ValueError, TypeError):
            return {}


def _render_or_fallback(env: Environment, template_name: str, context: dict, *, fallback: str) -> str:
    """Render a template, returning ``fallback`` on any error.

    The fallback path matters for two reasons:
      1. A missing template (typo in kind, file deleted) shouldn't
         block the alert from going out — the user still gets the
         critical info, just less polish.
      2. A template syntax error (Jinja2 raises) shouldn't crash the
         worker mid-batch.  Logged + skipped instead.
    """
    try:
        tmpl = env.get_template(template_name)
        return tmpl.render(**context)
    except TemplateNotFound:
        logger.warning(
            "[EmailTemplates] template not found: %s — using fallback",
            template_name,
        )
    except Exception:
        logger.exception(
            "[EmailTemplates] template render failed: %s", template_name,
        )
    return fallback


def _generic_body_text(notif, dashboard_url: str, unsubscribe_url: str) -> str:
    """Last-resort text body when the per-kind .body.txt.j2 is missing."""
    parts = [notif.title, "", notif.body]
    if notif.link:
        parts.extend(["", f"Open: {dashboard_url}{notif.link}"])
    parts.extend([
        "",
        "——",
        f"Unsubscribe: {unsubscribe_url}",
    ])
    return "\n".join(parts)


def _generic_body_html(notif) -> str:
    """Last-resort HTML body block when per-kind .body.html.j2 is missing."""
    # No string interpolation with .body / .title — those could contain
    # malicious chars.  Escape inline.
    from html import escape
    return (
        f'<h2 style="margin:0 0 16px;font-size:20px;font-weight:600;color:#111">'
        f'{escape(notif.title or "")}</h2>'
        f'<p style="margin:0;font-size:15px;line-height:1.6;color:#374151">'
        f'{escape(notif.body or "")}</p>'
    )
