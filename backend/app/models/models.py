from datetime import datetime, timedelta, timezone
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.core.database import Base


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String(100), unique=True, nullable=False, index=True)
    org_id = Column(String(100), nullable=False, index=True)
    node_id = Column(Integer, ForeignKey("camera_nodes.id"), nullable=True)
    name = Column(String(100), nullable=False)
    node_type = Column(String(20), default="unknown")
    capabilities = Column(String(500), default="streaming")
    group_id = Column(Integer, ForeignKey("camera_groups.id"), nullable=True)
    last_seen = Column(DateTime)
    # Pipeline state. In addition to the legacy "online" / "offline", the
    # CloudNode's FFmpeg supervisor now reports "starting", "streaming",
    # "restarting", "failed", and "error" so the UI can tell the user
    # why a camera they expect to be live isn't showing video.
    status = Column(String(20), default="offline")
    # Human-readable failure reason that goes alongside `status` when the
    # pipeline is `restarting` / `failed` / `error`. Cleared whenever the
    # node reports a healthy status.
    last_error = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None))

    # Codec detection fields
    video_codec = Column(String(50), nullable=True)  # e.g., "avc1.42e01e"
    audio_codec = Column(String(50), nullable=True)  # e.g., "mp4a.40.2"
    codec_detected_at = Column(DateTime, nullable=True)

    # Set by `app.core.plans.enforce_camera_cap` when the owning org's plan
    # cap would otherwise be exceeded. The oldest `max_cameras` cameras
    # (by `created_at`) keep `disabled_by_plan = False`; the rest are
    # flagged, and `POST /push-segment` rejects their uploads with
    # HTTP 402 + `plan_limit_hit` so the CloudNode can surface the
    # reason in its TUI. Flag is cleared on upgrade and on re-registration.
    # Default False so fresh installs and unaffected rows behave normally.
    disabled_by_plan = Column(Boolean, nullable=False, default=False, server_default="0")

    # Per-camera recording policy (v0.1.43+).  The heartbeat handler
    # computes this camera's target recording state per-tick from
    # ``continuous_24_7 OR (scheduled_recording AND in-window)`` and
    # echoes it back to CloudNode in the heartbeat response, which
    # reconciles its in-memory recording set to match.
    #
    # Replaces the previous org-level `Setting` rows for the same
    # toggles, which never actually drove anything (they persisted
    # but no consumer read them to start recording).  Per-camera is
    # both more flexible (privacy in bedroom + always-on in garage)
    # and the granularity that matches how recording_state is keyed
    # at runtime.
    continuous_24_7 = Column(Boolean, nullable=False, default=False, server_default="0")
    scheduled_recording = Column(Boolean, nullable=False, default=False, server_default="0")
    # "HH:MM" 24-hour strings; nullable so a fresh row doesn't have to
    # commit to a window before the operator opens the toggle.  When
    # ``scheduled_recording`` is true and either field is null, the
    # heartbeat handler treats the camera as "scheduled but not
    # configured" and skips recording — same effect as off.
    scheduled_start = Column(String(5), nullable=True)
    scheduled_end = Column(String(5), nullable=True)

    group = relationship("CameraGroup", back_populates="cameras")
    node = relationship("CameraNode", back_populates="cameras")

    @property
    def effective_status(self) -> str:
        """Return the real-time status based on last_seen.
        If no heartbeat in 90s (3 missed), the camera is offline."""
        if not self.last_seen or self.status == "offline":
            return "offline"
        age = datetime.now(tz=timezone.utc).replace(tzinfo=None) - self.last_seen
        if age > timedelta(seconds=90):
            return "offline"
        return self.status

    def to_dict(self):
        eff = self.effective_status
        # Only surface last_error when the camera is actually in a
        # broken state — once it flips back to streaming, the stale
        # reason would just confuse anyone reading the API response.
        err = self.last_error if eff in ("restarting", "failed", "error") else None
        return {
            "camera_id": self.camera_id,
            "name": self.name,
            # Parent node's *string* node_id (not the DB integer FK) so
            # frontend code can join cameras to nodes without a second
            # round-trip.  None when the camera row exists without a
            # registered node — vanishingly rare, but the cap-check
            # path can briefly leave a Camera with node_id=None during
            # node deletion.
            "node_id": self.node.node_id if self.node else None,
            # Human-readable node name (e.g. "Pi test", "Front yard").
            # Surfaced alongside node_id so the dashboard can show the
            # operator's chosen label rather than just the 8-char UUID
            # prefix.  None on an orphaned camera (rare; happens
            # transiently during node deletion when the cap-check path
            # leaves a Camera row with node_id=None).
            "node_name": self.node.name if self.node else None,
            "node_type": self.node_type,
            "capabilities": self.capabilities.split(",") if self.capabilities else [],
            "group": self.group.name if self.group else None,
            "status": eff,
            "last_error": err,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            # `true` when plan enforcement has suspended this camera.
            # Push-segment returns 402 while this is set; frontend shows a
            # locked-by-plan badge and an upgrade CTA.
            "disabled_by_plan": bool(self.disabled_by_plan),
            "recording_policy": {
                "continuous_24_7": bool(self.continuous_24_7),
                "scheduled_recording": bool(self.scheduled_recording),
                "scheduled_start": self.scheduled_start,
                "scheduled_end": self.scheduled_end,
            },
        }


class CameraGroup(Base):
    __tablename__ = "camera_groups"

    id = Column(Integer, primary_key=True)
    org_id = Column(String(100), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    color = Column(String(7), default="#22c55e")
    icon = Column(String(10), default="📁")
    created_at = Column(DateTime, default=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None))

    cameras = relationship("Camera", back_populates="group")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "icon": self.icon,
            "camera_count": len(self.cameras) if self.cameras else 0,
        }


class Setting(Base):
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True)
    org_id = Column(String(100), nullable=False, index=True)
    key = Column(String(100), nullable=False, index=True)
    value = Column(Text)
    updated_at = Column(DateTime, default=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None))

    @staticmethod
    def get(db, org_id: str, key: str, default: str = None) -> str:
        setting = db.query(Setting).filter_by(org_id=org_id, key=key).first()
        return setting.value if setting else default

    @staticmethod
    def get_many(db, org_id: str, keys_defaults: dict) -> dict:
        """Fetch multiple settings in a single query.
        keys_defaults: {key: default_value, ...}
        Returns: {key: value, ...}
        """
        rows = (
            db.query(Setting)
            .filter(Setting.org_id == org_id, Setting.key.in_(keys_defaults.keys()))
            .all()
        )
        found = {row.key: row.value for row in rows}
        return {k: found.get(k, default) for k, default in keys_defaults.items()}

    @staticmethod
    def set(db, org_id: str, key: str, value: str):
        setting = db.query(Setting).filter_by(org_id=org_id, key=key).first()
        if setting:
            setting.value = value
        else:
            setting = Setting(org_id=org_id, key=key, value=value)
            db.add(setting)
        db.commit()
        return setting


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True)
    org_id = Column(String(100), nullable=False, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None), index=True)
    event = Column(String(50), nullable=False, index=True)
    ip_address = Column(String(45))
    username = Column(String(80))
    user_id = Column(String(100))
    details = Column(Text)

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "event": self.event,
            "ip": self.ip_address,
            "username": self.username,
            "details": self.details,
        }


class CameraNode(Base):
    __tablename__ = "camera_nodes"

    id = Column(Integer, primary_key=True)
    node_id = Column(String(100), unique=True, nullable=False, index=True)
    org_id = Column(String(100), nullable=False, index=True)
    api_key_hash = Column(String(128), nullable=False)
    name = Column(String(100), nullable=False)
    hostname = Column(String(100))
    local_ip = Column(String(45))
    http_port = Column(Integer, default=8080)
    status = Column(String(20), default="offline")
    last_seen = Column(DateTime)
    key_rotated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None))
    video_codec = Column(String(50), nullable=True)
    audio_codec = Column(String(50), nullable=True)
    codec_detected_at = Column(DateTime, nullable=True)
    # Surfaces the most recent registration / auth failure to the UI so
    # a node stuck in ``pending`` can show *why* it's stuck (bad API key,
    # plan limit hit, etc.) instead of the user staring at an opaque
    # status badge.  Cleared on successful re-registration.
    last_register_error = Column(String(500), nullable=True)
    last_register_error_at = Column(DateTime, nullable=True)
    # CloudNode-reported build version (e.g. "0.1.0") + when we last saw it.
    # Updated by both register and heartbeat; nullable so very old nodes that
    # pre-date version reporting can still register without failing migration.
    # Used by the dashboard to surface "update available" badges and by
    # versions.check_node_version() to gate registrations from too-old nodes.
    node_version = Column(String(50), nullable=True)
    version_checked_at = Column(DateTime, nullable=True)

    # Filesystem-aware storage stats reported by CloudNode on heartbeat
    # (v0.1.41+).  Used by Settings → Camera Nodes to render a per-node
    # usage bar (used vs configured cap) and warn when the underlying
    # host disk is filling up.  All four are nullable so v0.1.40 and
    # earlier nodes still register / heartbeat without failing migration.
    storage_used_bytes = Column(BigInteger, nullable=True)
    storage_max_bytes = Column(BigInteger, nullable=True)
    storage_disk_free_bytes = Column(BigInteger, nullable=True)
    storage_disk_total_bytes = Column(BigInteger, nullable=True)
    storage_reported_at = Column(DateTime, nullable=True)

    cameras = relationship(
        "Camera", back_populates="node", cascade="all, delete-orphan"
    )

    @property
    def effective_status(self) -> str:
        """Return the real-time status based on last_seen.
        If no heartbeat in 90s (3 missed), the node is offline."""
        if not self.last_seen or self.status in ("offline", "pending"):
            return self.status or "offline"
        age = datetime.now(tz=timezone.utc).replace(tzinfo=None) - self.last_seen
        if age > timedelta(seconds=90):
            return "offline"
        return self.status

    def to_dict(self):
        return {
            "node_id": self.node_id,
            "name": self.name,
            "hostname": self.hostname,
            "local_ip": self.local_ip,
            "http_port": self.http_port,
            "status": self.effective_status,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "key_rotated_at": self.key_rotated_at.isoformat()
            if self.key_rotated_at
            else None,
            "camera_count": len(self.cameras) if self.cameras else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "video_codec": self.video_codec,
            "audio_codec": self.audio_codec,
            "last_register_error": self.last_register_error,
            "last_register_error_at": self.last_register_error_at.isoformat()
            if self.last_register_error_at
            else None,
            "node_version": self.node_version,
            "version_checked_at": self.version_checked_at.isoformat()
            if self.version_checked_at
            else None,
            "storage": {
                "used_bytes": self.storage_used_bytes,
                "max_bytes": self.storage_max_bytes,
                "disk_free_bytes": self.storage_disk_free_bytes,
                "disk_total_bytes": self.storage_disk_total_bytes,
                "reported_at": self.storage_reported_at.isoformat()
                if self.storage_reported_at
                else None,
            } if self.storage_reported_at else None,
        }


class StreamAccessLog(Base):
    __tablename__ = "stream_access_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(100), nullable=False, index=True)
    user_email = Column(String(255), default="")
    org_id = Column(String(100), nullable=False, index=True)
    camera_id = Column(String(100), nullable=False, index=True)
    node_id = Column(String(100), nullable=False)
    ip_address = Column(String(45))
    user_agent = Column(String(500))
    accessed_at = Column(DateTime, default=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None), index=True)

    # Composite index for the hot audit-log query pattern in
    # api/audit.py: WHERE org_id = ? AND accessed_at >= ? ORDER BY
    # accessed_at DESC (and the activity-aggregate variants that
    # filter org_id + accessed_at then group_by something else).
    # Single-column indexes on each column already exist above, but a
    # composite lets SQLite (and Postgres if we ever migrate) do a
    # straight index range-scan instead of intersecting two
    # single-column index hits, which materially matters once an org
    # has > a few thousand log rows.  SQLAlchemy create_all() is
    # idempotent — adding this index applies on the next boot.
    __table_args__ = (
        Index("ix_stream_access_logs_org_accessed", "org_id", "accessed_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_email": self.user_email or "",
            "org_id": self.org_id,
            "camera_id": self.camera_id,
            "node_id": self.node_id,
            "ip_address": self.ip_address,
            "accessed_at": self.accessed_at.isoformat(),
        }


class McpApiKey(Base):
    __tablename__ = "mcp_api_keys"

    id = Column(Integer, primary_key=True)
    org_id = Column(String(100), nullable=False, index=True)
    key_hash = Column(String(128), nullable=False, unique=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None))
    last_used_at = Column(DateTime, nullable=True)
    revoked = Column(Boolean, default=False)

    # Scope configuration — controls which MCP tools this key can invoke.
    #   scope_mode = "all"       → every tool is allowed (default for existing keys)
    #   scope_mode = "readonly"  → only read-classified tools (no mutations)
    #   scope_mode = "custom"    → scope_tools holds a JSON list of allowed tool names
    # A NULL scope_mode behaves like "all" so legacy rows keep working.
    scope_mode = Column(String(20), nullable=True, default="all")
    scope_tools = Column(Text, nullable=True)

    def get_scope_tools(self) -> list[str]:
        """Return the parsed scope_tools list, or [] if unset/invalid."""
        if not self.scope_tools:
            return []
        import json
        try:
            val = json.loads(self.scope_tools)
            if isinstance(val, list):
                return [str(v) for v in val]
        except (ValueError, TypeError):
            pass
        return []

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "revoked": self.revoked,
            "scope_mode": self.scope_mode or "all",
            "scope_tools": self.get_scope_tools(),
        }


class McpActivityLog(Base):
    __tablename__ = "mcp_activity_logs"

    id = Column(Integer, primary_key=True)
    org_id = Column(String(100), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False, index=True)
    key_name = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False)
    duration_ms = Column(Integer)
    args_summary = Column(String(500))
    error = Column(String(500))
    timestamp = Column(DateTime, default=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None), index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "org_id": self.org_id,
            "tool_name": self.tool_name,
            "key_name": self.key_name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "args_summary": self.args_summary,
            "error": self.error,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


# ---------------------------------------------------------------------------
# AI-generated incident reports
# ---------------------------------------------------------------------------

INCIDENT_SEVERITIES = ("low", "medium", "high", "critical")
INCIDENT_STATUSES = ("open", "acknowledged", "resolved", "dismissed")


class Incident(Base):
    """An incident report — typically authored by an MCP agent investigating
    suspicious activity, but reviewable + actionable from the dashboard."""

    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True)
    org_id = Column(String(100), nullable=False, index=True)
    camera_id = Column(String(100), nullable=True, index=True)
    title = Column(String(200), nullable=False)
    summary = Column(Text, nullable=False)
    report = Column(Text, default="")
    severity = Column(String(20), nullable=False, default="medium", index=True)
    status = Column(String(20), nullable=False, default="open", index=True)
    created_by = Column(String(150), nullable=False)  # mcp:<key_name> or user:<clerk_id>
    created_at = Column(DateTime, default=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None), index=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None))
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(150), nullable=True)

    evidence = relationship(
        "IncidentEvidence",
        back_populates="incident",
        cascade="all, delete-orphan",
        order_by="IncidentEvidence.timestamp",
    )

    def to_dict(self, include_evidence: bool = False) -> dict:
        d = {
            "id": self.id,
            "camera_id": self.camera_id,
            "title": self.title,
            "summary": self.summary,
            "report": self.report or "",
            "severity": self.severity,
            "status": self.status,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": self.resolved_by,
            "evidence_count": len(self.evidence) if self.evidence is not None else 0,
        }
        if include_evidence:
            d["evidence"] = [e.to_dict() for e in self.evidence]
        return d


class IncidentEvidence(Base):
    """A piece of evidence attached to an incident: a snapshot, a text
    observation, or a logged action the agent took."""

    __tablename__ = "incident_evidence"

    id = Column(Integer, primary_key=True)
    incident_id = Column(Integer, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(20), nullable=False)  # "snapshot" | "observation" | "action"
    text = Column(Text, nullable=True)
    camera_id = Column(String(100), nullable=True)
    data = Column(LargeBinary, nullable=True)
    data_mime = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None))

    incident = relationship("Incident", back_populates="evidence")

    def to_dict(self) -> dict:
        # Never inline blob bytes — clients fetch them separately.
        return {
            "id": self.id,
            "incident_id": self.incident_id,
            "kind": self.kind,
            "text": self.text,
            "camera_id": self.camera_id,
            "has_data": self.data is not None,
            "data_mime": self.data_mime,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class MotionEvent(Base):
    """A motion detection event reported by a CloudNode.

    Created when a node's FFmpeg scene-change analysis exceeds the
    configured threshold for a camera segment.
    """

    __tablename__ = "motion_events"

    id = Column(Integer, primary_key=True)
    org_id = Column(String(100), nullable=False, index=True)
    camera_id = Column(String(100), nullable=False, index=True)
    node_id = Column(String(100), nullable=False, index=True)
    score = Column(Integer, nullable=False)  # 0-100 (normalised)
    segment_seq = Column(Integer, nullable=True)
    timestamp = Column(
        DateTime,
        default=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None),
        index=True,
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "camera_id": self.camera_id,
            "node_id": self.node_id,
            "score": self.score,
            "segment_seq": self.segment_seq,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class Notification(Base):
    """A user-facing notification in the org inbox.

    Unified feed for motion detection, camera/node status transitions,
    and (future) system errors.  Read state is tracked per-user via
    ``UserNotificationState.last_viewed_at``.
    """

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    org_id = Column(String(100), nullable=False, index=True)

    # Event type discriminator, e.g.
    #   "motion", "camera_offline", "camera_online",
    #   "node_offline", "node_online", "error"
    kind = Column(String(40), nullable=False, index=True)

    # Who should see this.  "all" = every member of the org,
    # "admin" = only users with admin role.  The inbox endpoint
    # filters based on the caller's role.
    audience = Column(String(20), nullable=False, default="all")

    # Display copy
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False, default="")

    # "info" | "warning" | "error" | "critical"
    severity = Column(String(20), nullable=False, default="info", index=True)

    # Optional deep-link (relative path) so clicking the notification
    # jumps to a camera / incident / settings page.
    link = Column(String(500), nullable=True)

    # Optional subject references (kept as strings, not FKs, so a notification
    # still renders even if the camera or node is later deleted).
    camera_id = Column(String(100), nullable=True, index=True)
    node_id = Column(String(100), nullable=True, index=True)

    # Free-form extra data as a JSON string (e.g. motion score, segment_seq).
    # Kept small — not meant to be queried, just rendered.
    meta_json = Column(Text, nullable=True)

    created_at = Column(
        DateTime,
        default=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None),
        index=True,
    )

    def to_dict(self) -> dict:
        import json as _json
        meta = None
        if self.meta_json:
            try:
                meta = _json.loads(self.meta_json)
            except (ValueError, TypeError):
                meta = None
        return {
            "id": self.id,
            "kind": self.kind,
            "audience": self.audience,
            "title": self.title,
            "body": self.body,
            "severity": self.severity,
            "link": self.link,
            "camera_id": self.camera_id,
            "node_id": self.node_id,
            "meta": meta,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class UserNotificationState(Base):
    """Per-user read-state for the notification inbox.

    One row per (Clerk user, org) combination.

    ``last_viewed_at`` is bumped when the user opens the notification
    panel; the unread count is computed as
    ``COUNT(*) WHERE created_at > last_viewed_at``.

    ``cleared_at`` is bumped when the user clicks "Clear all" — the
    inbox list then hides everything with ``created_at <= cleared_at``.
    Soft-hide (per user) rather than hard-delete (org-wide) so one
    user clearing their view doesn't erase history for teammates or
    for incidents/audit queries.  Nullable so pre-existing rows don't
    need a backfill; ``None`` means "never cleared".
    """

    __tablename__ = "user_notification_state"

    id = Column(Integer, primary_key=True)
    clerk_user_id = Column(String(100), nullable=False, index=True)
    org_id = Column(String(100), nullable=False, index=True)
    last_viewed_at = Column(
        DateTime,
        default=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None),
    )
    cleared_at = Column(DateTime, nullable=True)

    __table_args__ = (
        # One read-state row per user per org.
        UniqueConstraint("clerk_user_id", "org_id", name="uq_user_notif_state_user_org"),
    )


class ProcessedWebhook(Base):
    """Dedupe ledger for incoming Clerk webhooks.

    Svix (Clerk's webhook signer) retries on any non-2xx response and on
    network failure.  Without idempotency, a transient hiccup in our
    handler can cause Clerk to redeliver the SAME ``user.created`` /
    ``subscription.updated`` event, and the handler would re-run all
    its side effects (re-set member limits, re-upsert plan settings,
    re-fire enforce_camera_cap).  Most operations are upserts so
    re-running is benign, but anything that reads-then-writes is at
    risk of doubling — and the fix is cheap.

    The ``svix_msg_id`` is the unique message identifier Svix sends in
    the ``svix-id`` header on every delivery (same id across retries).
    Insert at the end of successful handler execution; future retries
    short-circuit on lookup.

    Cleanup: a periodic sweep can drop rows older than 30 days
    (Svix's max retry window is 5 days, so 30d is comfortable).
    """

    __tablename__ = "processed_webhooks"

    id = Column(Integer, primary_key=True)
    svix_msg_id = Column(String(255), nullable=False, unique=True, index=True)
    event_type = Column(String(100), default="")
    processed_at = Column(
        DateTime,
        default=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None),
        index=True,
    )


class OrgMonthlyUsage(Base):
    """Per-org viewer-seconds counter, bucketed by calendar month (UTC).

    Used to enforce per-tier monthly viewer-hour caps (see
    ``PLAN_LIMITS[plan]["max_viewer_hours_per_month"]``). Each cached HLS
    segment served to an authenticated viewer is ~1 second of video, so
    the counter increments by 1 per successful segment delivery.

    Writes happen out-of-band from the request path: a process-local
    in-memory accumulator (see ``app.api.hls.flush_viewer_usage``) flushes
    pending increments every ~60 seconds with a single UPSERT per org, so
    the hot HLS-serve path never touches the DB. Cap-enforcement reads the
    cached total + the pending in-memory delta before serving, so an org
    that's currently blowing past its cap gets blocked on the next segment.

    ``year_month`` is stored as a ``YYYY-MM`` string for clean
    human-readable debugging and trivial month-rollover queries. The
    ``(org_id, year_month)`` uniqueness guarantee is what makes the
    background UPSERT safe.
    """

    __tablename__ = "org_monthly_usage"

    id = Column(Integer, primary_key=True)
    org_id = Column(String(100), nullable=False, index=True)
    year_month = Column(String(7), nullable=False)  # "YYYY-MM"
    viewer_seconds = Column(Integer, nullable=False, default=0)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(tz=timezone.utc).replace(tzinfo=None),
    )

    __table_args__ = (
        UniqueConstraint("org_id", "year_month", name="uq_org_monthly_usage"),
    )

    def to_dict(self) -> dict:
        return {
            "org_id": self.org_id,
            "year_month": self.year_month,
            "viewer_seconds": self.viewer_seconds,
            "viewer_hours": round(self.viewer_seconds / 3600.0, 2),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


