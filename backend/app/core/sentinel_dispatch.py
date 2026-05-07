"""
Sentinel dispatch — decides whether a notification should create a
pending agent run, and inserts the row when yes.

The agent service itself doesn't yet exist (slice 3), but the
dispatcher does — pending rows queue up in `sentinel_runs` and the
agent will pick them up when it ships. This module is the single
gate that enforces:

  - is Sentinel enabled for this org?
  - is the trigger this notification kind belongs to enabled?
  - is the camera in scope?
  - does the schedule allow runs right now?
  - is the org under the monthly cap?

If all five answer yes → INSERT a pending sentinel_runs row and
return it. Otherwise no-op.

This is also the helper the manual "Run now" endpoint calls to bypass
some checks (the operator's manual click skips the schedule + scope
gates intentionally — the operator overrode them on purpose by clicking).

Cap enforcement: 300 runs per calendar month per org. The cap value
is hard-coded for now — slice 5 will surface it as a per-plan setting
if/when we offer multiple Pro Plus tiers.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.models import SentinelConfig, SentinelRun, Setting

logger = logging.getLogger(__name__)


# 300 runs / month is generous for typical use (10/day) — see plans/
# for the rationale. Hard-coded until slice 5 introduces per-plan caps.
MONTHLY_RUN_CAP = 300


# Notification kinds that map to a Sentinel trigger.  Keys are
# notification kind strings; values are the SentinelConfig boolean
# field that has to be on for the trigger to fire.
_KIND_TO_TRIGGER_FIELD: dict[str, str] = {
    "motion": "motion_enabled",
    # incident_created is the kind emitted when a human files an
    # incident.  See _NOTIFICATION_KIND_TO_SETTING in notifications.py
    # — the kind string predates the more readable "incident_opened"
    # we use in the UI; we map to the same trigger here.
    "incident_created": "incident_opened_enabled",
}

# Map back from trigger field → run trigger_type label that lands in
# sentinel_runs.trigger_type. Keep in sync with the frontend trigger
# pill colour mapping (.sentinel-trigger-pill-*).
_FIELD_TO_TRIGGER_TYPE = {
    "motion_enabled": "motion",
    "incident_opened_enabled": "incident_opened",
}


def _start_of_month_utc() -> datetime:
    now = datetime.now(tz=UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


def runs_used_this_month(db: Session, org_id: str) -> int:
    """Count of sentinel runs for this org in the current calendar
    month.  Includes pending + running + terminal — every dispatch
    counts against the cap regardless of outcome."""
    return (
        db.query(SentinelRun)
        .filter(
            SentinelRun.org_id == org_id,
            SentinelRun.triggered_at >= _start_of_month_utc(),
        )
        .count()
    )


def cap_remaining(db: Session, org_id: str) -> int:
    return max(0, MONTHLY_RUN_CAP - runs_used_this_month(db, org_id))


def _is_camera_in_scope(scope_dict: dict | None, camera_id: str | None) -> bool:
    """Cameras absent from camera_scope default to in-scope (True).
    This matches the SentinelConfig docstring and the frontend's
    isCameraInScope helper — new cameras don't silently disappear
    from the agent's purview when added.
    """
    if not camera_id:
        # Triggers without a camera (e.g. scheduled all-camera sweeps)
        # are always considered in scope — the agent decides which
        # cameras to investigate.
        return True
    if not scope_dict:
        return True
    return scope_dict.get(camera_id) is not False


def _schedule_allows_now(cfg: SentinelConfig, db: Session) -> bool:
    """Is right-now within the configured schedule window?

    "always" mode: yes.
    "off" mode: no.
    "scheduled" mode: yes iff today is an active day AND the current
    hour is within the start..end window.  Times are interpreted in
    the org's timezone (Setting key 'timezone', defaults to UTC).
    """
    mode = cfg.schedule_mode or "always"
    if mode == "always":
        return True
    if mode == "off":
        return False

    # scheduled mode — check window + day-of-week
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    tz_name = Setting.get(db, cfg.org_id, "timezone", "UTC") or "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")

    now_local = datetime.now(tz=tz)
    day_keys = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    today_key = day_keys[now_local.weekday()]

    active_days = cfg.get_active_days()
    if today_key not in active_days:
        return False

    # Parse HH:MM strings; defensive — fall back to wide-open if
    # the values are bad.
    def _parse_hh(value: str, default: int) -> int:
        try:
            return int(value.split(":")[0])
        except (AttributeError, ValueError, IndexError):
            return default

    start_h = _parse_hh(cfg.schedule_start or "00:00", 0)
    end_h = _parse_hh(cfg.schedule_end or "24:00", 24)
    cur_h = now_local.hour

    if start_h < end_h:
        return start_h <= cur_h < end_h
    # Wrap-around (e.g. 22:00 → 06:00)
    return cur_h >= start_h or cur_h < end_h


def _can_dispatch_for_kind(
    cfg: SentinelConfig,
    kind: str,
    camera_id: Optional[str],
    db: Session,
) -> tuple[bool, str]:
    """Run the full dispatch gate.  Returns (ok, reason)."""
    if not cfg.enabled:
        return False, "sentinel_disabled"

    field = _KIND_TO_TRIGGER_FIELD.get(kind)
    if field is None:
        return False, "kind_not_a_sentinel_trigger"

    if not getattr(cfg, field, False):
        return False, f"trigger_{field}_off"

    if not _is_camera_in_scope(cfg.get_camera_scope(), camera_id):
        return False, "camera_out_of_scope"

    if not _schedule_allows_now(cfg, db):
        return False, "outside_schedule_window"

    if cap_remaining(db, cfg.org_id) <= 0:
        return False, "monthly_cap_reached"

    return True, "ok"


def maybe_dispatch_for_notification(
    db: Session,
    org_id: str,
    kind: str,
    camera_id: Optional[str] = None,
) -> Optional[SentinelRun]:
    """Called from create_notification() — best-effort dispatch.

    Returns the new SentinelRun row if the gate allowed dispatch,
    None otherwise. Never raises (a failed dispatch must NEVER block
    the underlying notification from being delivered to the inbox or
    email channels).
    """
    try:
        cfg = db.query(SentinelConfig).filter_by(org_id=org_id).first()
        if cfg is None:
            return None  # No config = Sentinel never configured = no dispatch

        ok, reason = _can_dispatch_for_kind(cfg, kind, camera_id, db)
        if not ok:
            logger.debug(
                "sentinel: dispatch skipped org=%s kind=%s camera=%s reason=%s",
                org_id, kind, camera_id, reason,
            )
            return None

        trigger_type = _FIELD_TO_TRIGGER_TYPE.get(_KIND_TO_TRIGGER_FIELD[kind], kind)
        run = SentinelRun(
            id=uuid.uuid4().hex,
            org_id=org_id,
            triggered_at=datetime.now(tz=UTC).replace(tzinfo=None),
            trigger_type=trigger_type,
            camera_id=camera_id,
            tool_call_count=0,
            outcome="pending",
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        logger.info(
            "sentinel: dispatched pending run id=%s org=%s trigger=%s camera=%s",
            run.id, org_id, trigger_type, camera_id,
        )
        return run
    except Exception:  # noqa: BLE001
        # Dispatch failure must NOT cascade into the notification path.
        # A run that should have queued is regrettable; an unhandled
        # exception that 500s on a motion event is far worse.
        logger.exception("sentinel: dispatch failed silently org=%s kind=%s", org_id, kind)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


def dispatch_manual_run(
    db: Session,
    org_id: str,
    prompt: str,
    camera_id: Optional[str] = None,
) -> SentinelRun:
    """Operator-initiated run from the "Run now" button.

    Skips the schedule + scope checks (the operator overrode those
    by clicking), but still enforces the cap. Sentinel doesn't have
    to be enabled either — the operator can run a one-off check on
    a paused agent.

    Raises ValueError on cap exhaustion so the API endpoint can
    surface the right HTTP status.
    """
    # Ensure config exists so the manual-run path works for orgs that
    # have never opened the Sentinel page (an unusual case but
    # possible).
    cfg = db.query(SentinelConfig).filter_by(org_id=org_id).first()
    if cfg is None:
        cfg = SentinelConfig(org_id=org_id)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)

    if cap_remaining(db, org_id) <= 0:
        raise ValueError("monthly_cap_reached")

    run = SentinelRun(
        id=uuid.uuid4().hex,
        org_id=org_id,
        triggered_at=datetime.now(tz=UTC).replace(tzinfo=None),
        trigger_type="manual",
        camera_id=camera_id,
        tool_call_count=0,
        outcome="pending",
        manual_prompt=(prompt or "")[:2000],  # bound prompt size
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info(
        "sentinel: manual run id=%s org=%s camera=%s prompt_len=%d",
        run.id, org_id, camera_id, len(prompt or ""),
    )
    return run
