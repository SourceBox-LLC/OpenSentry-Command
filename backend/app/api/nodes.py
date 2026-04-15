import hashlib
import logging
import uuid as uuid_mod
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.audit import audit_label, write_audit
from app.core.codec import sanitize_video_codec
from app.core.database import get_db
from app.core.auth import AuthUser, require_admin, require_active_billing, get_current_user
from app.core.limiter import limiter
from app.core.plans import get_plan_limits, get_plan_limits_for_org, get_plan_display_name
from app.core.versions import check_node_version
from app.models.models import CameraNode, Camera, Setting
from app.schemas.schemas import NodeRegister, NodeHeartbeat, CameraReport, NodeCreate
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


_PLAN_LIMIT_NOTIF_THROTTLE_SECONDS = 3600  # 1 hour between plan-limit notifications


def _emit_plan_limit_notification(
    db: Session,
    org_id: str,
    limits: dict,
    *,
    skipped: list[str],
) -> None:
    """Emit a one-per-hour inbox notification when plan cap rejects cameras.

    Debounced via a Setting row so a node re-heartbeating every 30s with
    an over-cap camera list doesn't spam admins.  Best-effort: any
    failure is swallowed because the caller's happy path (node
    registration) must not depend on the notification layer.
    """
    try:
        now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        last_at_str = Setting.get(db, org_id, "plan_limit_notif_last_at")
        if last_at_str:
            try:
                last_at = datetime.fromisoformat(last_at_str)
                if (now - last_at).total_seconds() < _PLAN_LIMIT_NOTIF_THROTTLE_SECONDS:
                    return
            except ValueError:
                pass  # malformed timestamp — treat as never emitted

        plan_name = get_plan_display_name(limits.get("_plan", "free_org"))
        # Local import to avoid a circular dep at module load time.
        from app.api.notifications import create_notification

        create_notification(
            org_id=org_id,
            kind="plan_limit_reached",
            title=f"Camera limit reached on {plan_name}",
            body=(
                f"Your node reported cameras beyond the {limits['max_cameras']}-camera "
                f"limit. Skipped: {', '.join(skipped[:5])}"
                + (f" (+{len(skipped) - 5} more)" if len(skipped) > 5 else "")
                + ". Upgrade to add them."
            ),
            severity="warning",
            audience="admin",
            link="/settings",
            meta={
                "plan": plan_name,
                "max_cameras": limits["max_cameras"],
                "skipped": skipped,
            },
            db=db,
        )
        Setting.set(db, org_id, "plan_limit_notif_last_at", now.isoformat())
    except Exception:
        logger.exception("Failed to emit plan-limit notification for org %s", org_id)


def _record_node_register_error(db: Session, node: CameraNode, reason: str) -> None:
    """Persist a registration/auth failure on the node row so the UI can
    show *why* a node is stuck in ``pending`` instead of making the user
    SSH in to read CloudNode logs.  Best-effort: any DB error is swallowed
    because the caller is already about to raise a 4xx to the node."""
    try:
        node.last_register_error = reason[:500]
        node.last_register_error_at = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        db.commit()
    except Exception:
        logger.exception("Failed to persist last_register_error for node %s", node.node_id)
        db.rollback()


@router.post("/validate")
@limiter.limit("10/minute")
async def validate_node(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Validate a node_id + API key pair.
    Called by the CloudNode setup wizard before saving configuration.
    Returns the node name on success so the wizard can confirm the right node.
    """
    api_key = request.headers.get("X-Node-API-Key")
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    node_id = body.get("node_id")
    if not node_id:
        raise HTTPException(status_code=400, detail="node_id is required")

    node = db.query(CameraNode).filter_by(node_id=node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")

    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    if node.api_key_hash != api_key_hash:
        _record_node_register_error(
            db, node,
            "Invalid API key — rotate the key in Settings and re-run the installer.",
        )
        raise HTTPException(status_code=403, detail="Invalid API key for this node")

    return {"success": True, "node_id": node.node_id, "name": node.name}


@router.post("/register")
@limiter.limit("10/minute")
async def register_node(
    request: Request,
    data: NodeRegister,
    db: Session = Depends(get_db),
):
    logger.info("Registration attempt from node_id=%s", data.node_id)
    api_key = request.headers.get("X-Node-API-Key")

    logger.debug("API key present: %s", bool(api_key))

    if not api_key:
        logger.warning("Registration rejected: no API key provided")
        raise HTTPException(status_code=401, detail="API key required")

    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    # Defensive sanitization — older CloudNode builds (v0.1.5 and earlier)
    # shipped garbage `avc1.*e00a` H.264 strings for the Pi's
    # h264_v4l2m2m encoder.  Upgrade before persisting so the next playlist
    # fetch doesn't brick the browser MSE attach.  See core/codec.py.
    sanitized_video_codec = sanitize_video_codec(data.video_codec) if data.video_codec else None

    existing_node = db.query(CameraNode).filter_by(node_id=data.node_id).first()

    if existing_node:
        logger.info("Found existing node id=%s, org=%s", existing_node.id, existing_node.org_id)
        if existing_node.api_key_hash != api_key_hash:
            logger.warning("Registration rejected: API key mismatch for node %s", data.node_id)
            _record_node_register_error(
                db, existing_node,
                "Invalid API key during registration — rotate the key in Settings and re-run the installer.",
            )
            raise HTTPException(status_code=403, detail="Invalid API key for this node")

        # Refuse registrations from CloudNodes too old to speak the current
        # wire protocol — they'd just keep failing in subtle ways downstream
        # and the operator would have no idea what's wrong.  HTTP 426 with
        # the canonical "you need at least X" payload makes the next step
        # obvious.  Persisted on the node row so the dashboard can surface
        # the bad version even for nodes that get rejected here.
        version_check = check_node_version(data.node_version)
        existing_node.node_version = version_check["parsed"] if data.node_version else None
        existing_node.version_checked_at = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        if not version_check["supported"]:
            _record_node_register_error(
                db, existing_node,
                f"CloudNode version {version_check['parsed']} is below the minimum "
                f"supported {version_check['min_supported']}. Update CloudNode to "
                f"{version_check['latest']} and re-register.",
            )
            raise HTTPException(
                status_code=426,
                detail={
                    "message": (
                        f"CloudNode {version_check['parsed']} is no longer supported. "
                        f"Minimum: {version_check['min_supported']}, "
                        f"latest: {version_check['latest']}."
                    ),
                    "reported": version_check["reported"],
                    "min_supported": version_check["min_supported"],
                    "latest": version_check["latest"],
                },
            )

        existing_node.hostname = data.hostname or existing_node.hostname
        existing_node.local_ip = data.local_ip or existing_node.local_ip
        existing_node.http_port = data.http_port or existing_node.http_port
        existing_node.status = "online"
        existing_node.last_seen = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        # Successful re-registration: clear any stale error from an
        # earlier bad-key attempt so the UI stops flagging it.
        existing_node.last_register_error = None
        existing_node.last_register_error_at = None

        if data.video_codec:
            existing_node.video_codec = sanitized_video_codec
            existing_node.audio_codec = data.audio_codec
            existing_node.codec_detected_at = datetime.now(tz=timezone.utc).replace(tzinfo=None)

        # Enforce camera cap: count existing org cameras vs plan limit
        org_id = existing_node.org_id
        limits = get_plan_limits_for_org(db, org_id)
        current_cameras = db.query(Camera).filter_by(org_id=org_id).count()

        # Map device_path to camera_id for response
        camera_mapping = {}
        new_camera_count = 0
        skipped_cameras: list[str] = []  # surfaces plan-limit hits in the response

        for cam_data in data.cameras or []:
            # Generate camera_id from node_id and device_path
            device_path = cam_data.device_path or cam_data.camera_id or "unknown"
            # Sanitize device_path for use as camera_id.
            # Replace path separators AND spaces so IDs are URL-safe.
            sanitized_device = (
                device_path.replace("/", "_")
                .replace("\\", "_")
                .replace(" ", "_")
                .strip("_")
            )
            camera_id = f"{data.node_id}_{sanitized_device}"

            logger.debug("Processing camera: device_path=%s -> camera_id=%s", device_path, camera_id)

            camera_mapping[device_path] = camera_id

            existing_cam = db.query(Camera).filter_by(camera_id=camera_id).first()
            if existing_cam:
                logger.debug("Updating existing camera %s", camera_id)
                existing_cam.name = cam_data.name or existing_cam.name
                existing_cam.last_seen = datetime.now(tz=timezone.utc).replace(tzinfo=None)
                existing_cam.status = "online"
                if data.video_codec:
                    existing_cam.video_codec = sanitized_video_codec
                    existing_cam.audio_codec = data.audio_codec
            else:
                # Check camera cap before creating
                if current_cameras + new_camera_count >= limits["max_cameras"]:
                    plan_name = get_plan_display_name(limits.get("_plan", "free_org"))
                    logger.warning(
                        "Camera limit reached for org %s (%d/%d on %s plan), skipping camera %s",
                        org_id, current_cameras + new_camera_count, limits["max_cameras"], plan_name, camera_id,
                    )
                    skipped_cameras.append(cam_data.name or sanitized_device)
                    continue

                logger.debug("Creating new camera %s", camera_id)
                new_cam = Camera(
                    camera_id=camera_id,
                    org_id=existing_node.org_id,
                    node_id=existing_node.id,
                    name=cam_data.name or f"Camera {sanitized_device}",
                    node_type=cam_data.node_type or "usb",
                    capabilities=",".join(cam_data.capabilities)
                    if cam_data.capabilities
                    else "streaming",
                    status="online",
                    last_seen=datetime.now(tz=timezone.utc).replace(tzinfo=None),
                    video_codec=sanitized_video_codec,
                    audio_codec=data.audio_codec,
                    codec_detected_at=datetime.now(tz=timezone.utc).replace(tzinfo=None) if data.video_codec else None,
                )
                db.add(new_cam)
                new_camera_count += 1

        # Remove stale camera records that are no longer reported by this node.
        # This handles cases where old camera_ids (e.g. with spaces) linger after
        # a sanitization fix or a device is removed.
        current_camera_ids = set(camera_mapping.values())
        all_node_cameras = db.query(Camera).filter_by(node_id=existing_node.id).all()
        for stale_cam in all_node_cameras:
            if stale_cam.camera_id not in current_camera_ids:
                logger.info("Removing stale camera record: %s", stale_cam.camera_id)
                from app.api.hls import cleanup_camera_cache
                cleanup_camera_cache(stale_cam.camera_id)
                db.delete(stale_cam)

        db.commit()
        logger.info("Node %s re-registered successfully with %d cameras", data.node_id, len(camera_mapping))

        # If the plan cap rejected any cameras, emit an admin notification
        # and tell the CloudNode so it can surface the hit to the installer.
        # Debounce at 1 hour so a node that keeps re-heartbeating with an
        # over-cap camera list doesn't flood the inbox.
        if skipped_cameras:
            _emit_plan_limit_notification(
                db, org_id, limits, skipped=skipped_cameras,
            )

        response = {
            "success": True,
            "node_id": existing_node.node_id,
            "node_secret": api_key,
            "status": "updated",
            "message": "Node re-registered successfully",
            "cameras": camera_mapping,
        }
        if skipped_cameras:
            plan_name = get_plan_display_name(limits.get("_plan", "free_org"))
            response["plan_limit_hit"] = {
                "plan": plan_name,
                "max_cameras": limits["max_cameras"],
                "skipped": skipped_cameras,
                "detail": (
                    f"Plan limit reached ({limits['max_cameras']} on {plan_name}). "
                    f"Upgrade to add: {', '.join(skipped_cameras)}."
                ),
            }
        # Tell the node when a newer release is available.  CloudNode logs this
        # as a one-line warning and the dashboard turns it into an
        # "update available" badge on the node row.  We don't push the update
        # ourselves — operators install CloudNode on their own hardware.
        if version_check["update_available"]:
            response["update_available"] = version_check["update_available"]
        return response

    logger.warning("Registration failed: node_id=%s not found in database", data.node_id)
    raise HTTPException(
        status_code=404,
        detail="Node not found. Create this node in the dashboard first.",
    )


@router.post("/heartbeat")
@limiter.limit("60/minute")
async def node_heartbeat(
    request: Request,
    data: NodeHeartbeat,
    db: Session = Depends(get_db),
):
    logger.debug("Heartbeat received from node_id=%s", data.node_id)
    api_key = request.headers.get("X-Node-API-Key")

    if not api_key:
        logger.warning("Heartbeat rejected: no API key provided for node %s", data.node_id)
        raise HTTPException(status_code=401, detail="API key required")

    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    node = db.query(CameraNode).filter_by(node_id=data.node_id).first()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    if node.api_key_hash != api_key_hash:
        raise HTTPException(status_code=403, detail="Invalid API key")

    # Same version gate as register — a CloudNode that gets upgraded to a
    # supported version recovers automatically on its next heartbeat; one
    # that gets *downgraded* below MIN_SUPPORTED stops being able to
    # heartbeat and shows up as offline within 90s.  Persist the reported
    # version on every heartbeat so the dashboard reflects in-place updates
    # without requiring a re-register.
    version_check = check_node_version(data.node_version)
    node.node_version = version_check["parsed"] if data.node_version else None
    node.version_checked_at = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    if not version_check["supported"]:
        raise HTTPException(
            status_code=426,
            detail={
                "message": (
                    f"CloudNode {version_check['parsed']} is no longer supported. "
                    f"Minimum: {version_check['min_supported']}, "
                    f"latest: {version_check['latest']}."
                ),
                "reported": version_check["reported"],
                "min_supported": version_check["min_supported"],
                "latest": version_check["latest"],
            },
        )

    node.status = "online"
    node.last_seen = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    node.local_ip = data.local_ip or node.local_ip

    camera_updates = data.cameras or []
    if camera_updates:
        camera_ids = [cs.camera_id for cs in camera_updates]
        cams = db.query(Camera).filter(
            Camera.camera_id.in_(camera_ids),
            Camera.node_id == node.id,
        ).all()
        cam_map = {c.camera_id: c for c in cams}
        now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        for cam_status in camera_updates:
            cam = cam_map.get(cam_status.camera_id)
            if cam:
                cam.status = cam_status.status
                cam.last_seen = now
                # Record (or clear) the pipeline failure reason. Healthy
                # states wipe the field so stale errors don't linger in
                # the API response after the supervisor recovers.
                if cam_status.status in ("restarting", "failed", "error"):
                    cam.last_error = cam_status.last_error
                else:
                    cam.last_error = None

    db.commit()

    response = {"success": True, "timestamp": datetime.now(tz=timezone.utc).replace(tzinfo=None).isoformat()}
    if version_check["update_available"]:
        response["update_available"] = version_check["update_available"]
    return response


@router.get("")
async def list_nodes(
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    # Attach the live ``update_available`` hint computed from the
    # currently-configured ``LATEST_NODE_VERSION`` so the dashboard can
    # render an "update available" badge without a second round-trip.
    # Computing at read time (rather than storing on the row) means a
    # bump to LATEST_NODE_VERSION takes effect for every existing node
    # on the next refresh — no migration, no background job.
    nodes = db.query(CameraNode).filter_by(org_id=user.org_id).all()
    result = []
    for n in nodes:
        d = n.to_dict()
        version_info = check_node_version(n.node_version)
        d["update_available"] = version_info["update_available"]
        d["latest_node_version"] = version_info["latest"]
        d["min_supported_node_version"] = version_info["min_supported"]
        d["version_supported"] = version_info["supported"]
        result.append(d)
    return result


@router.get("/plan")
async def get_plan_info(
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the org's current plan, usage, and limits."""
    from app.models.models import Setting

    limits = get_plan_limits(user.plan)
    current_nodes = db.query(CameraNode).filter_by(org_id=user.org_id).count()
    current_cameras = db.query(Camera).filter_by(org_id=user.org_id).count()
    payment_past_due = Setting.get(db, user.org_id, "payment_past_due", "false") == "true"
    return {
        "plan": user.plan,
        "plan_name": get_plan_display_name(user.plan),
        "features": user.features,
        "limits": limits,
        "usage": {
            "nodes": current_nodes,
            "cameras": current_cameras,
        },
        "payment_past_due": payment_past_due,
    }


@router.post("")
@limiter.limit("20/hour")
async def create_node(
    request: Request,
    data: NodeCreate,
    user: AuthUser = Depends(require_active_billing),
    db: Session = Depends(get_db),
):
    # Enforce node limit based on plan
    limits = get_plan_limits(user.plan)
    current_nodes = db.query(CameraNode).filter_by(org_id=user.org_id).count()
    if current_nodes >= limits["max_nodes"]:
        plan_name = get_plan_display_name(user.plan)
        raise HTTPException(
            status_code=403,
            detail=f"Node limit reached ({limits['max_nodes']} on {plan_name} plan). Upgrade your plan to add more nodes.",
        )

    node_id = str(uuid_mod.uuid4())[:8]
    api_key = str(uuid_mod.uuid4())
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    node = CameraNode(
        node_id=node_id,
        org_id=user.org_id,
        name=data.name or f"Node-{node_id}",
        api_key_hash=api_key_hash,
        status="pending",
    )
    db.add(node)
    db.commit()

    logger.info("Node created: node_id=%s, name=%s, org=%s", node_id, node.name, user.org_id)

    write_audit(
        db,
        org_id=user.org_id,
        event="node_created",
        user_id=user.user_id,
        username=audit_label(user),
        details={"node_id": node_id, "name": node.name},
        request=request,
    )

    return {
        "success": True,
        "node_id": node_id,
        "name": node.name,
        "api_key": api_key,
        "warning": "Store this API key securely. It cannot be retrieved again.",
    }


@router.get("/ws-status")
async def ws_status(
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Check which nodes are connected via WebSocket (filtered to this org)."""
    from app.api.ws import manager
    org_nodes = db.query(CameraNode.node_id).filter_by(org_id=user.org_id).all()
    org_node_ids = {n[0] for n in org_nodes}
    connected = [nid for nid in manager.connected_nodes if nid in org_node_ids]
    return {
        "connected_nodes": connected,
        "count": len(connected),
    }


@router.post("/self/decommission")
@limiter.limit("10/hour")
async def decommission_self(
    request: Request,
    db: Session = Depends(get_db),
):
    """Node-initiated decommission.

    Called when the operator runs ``/wipe confirm`` on the CloudNode TUI.
    The node asks us to delete its server-side record *before* it
    erases local state, so "factory reset" is one user action instead
    of "wipe locally, then remember to also delete it in the dashboard".

    Unlike the admin ``DELETE /{node_id}`` path, we skip the reflexive
    ``wipe_data`` WebSocket command — the node is the one asking, so
    it's already committed to wiping itself regardless of whether this
    response makes it back.

    Auth: ``X-Node-API-Key`` header. The node identifies itself by key
    rather than putting ``node_id`` in the URL — a stolen key can
    already register/heartbeat as that node, so there's no new
    exposure, and it keeps the endpoint independent of whether the
    caller still knows its own node_id after a partial reset.
    """
    api_key = request.headers.get("X-Node-API-Key")
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")

    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    node = db.query(CameraNode).filter_by(api_key_hash=api_key_hash).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Clean up in-memory caches for every camera on this node — same
    # cleanup the admin DELETE path does, so we don't leak a camera's
    # HLS segment cache after its owning node is gone.
    from app.api.hls import cleanup_camera_cache
    for camera in list(node.cameras):
        cleanup_camera_cache(camera.camera_id)

    node_id = node.node_id
    node_name = node.name
    org_id = node.org_id
    db.delete(node)
    db.commit()

    # Node-initiated — no acting admin. We still want the audit row
    # because a node disappearing is a security-relevant event, and
    # the ``initiated_by`` flag lets the UI distinguish this from the
    # admin-triggered delete above.
    write_audit(
        db,
        org_id=org_id,
        event="node_decommissioned",
        username=f"node:{node_id}",
        details={
            "node_id": node_id,
            "name": node_name,
            "initiated_by": "node",
        },
        request=request,
    )

    return {"success": True, "deleted": node_id}


@router.get("/{node_id}")
async def get_node(
    node_id: str,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    node = db.query(CameraNode).filter_by(node_id=node_id, org_id=user.org_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node.to_dict()


@router.delete("/{node_id}")
@limiter.limit("20/hour")
async def delete_node(
    node_id: str,
    request: Request,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    node = db.query(CameraNode).filter_by(node_id=node_id, org_id=user.org_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    # Tell the node to wipe all its local data before we delete server-side records.
    node_wiped = False
    try:
        from app.api.ws import manager
        result = await manager.send_command(node_id, "wipe_data", {}, timeout=10)
        if result and result.get("status") == "success":
            node_wiped = True
            logger.info("Node %s acknowledged local data wipe", node_id)
        else:
            logger.warning("Node %s wipe_data returned: %s", node_id, result)
    except Exception as e:
        # Node may be offline — proceed with server-side cleanup anyway.
        logger.warning("Could not send wipe_data to node %s (may be offline): %s", node_id, e)

    # Clean up in-memory caches for every camera on this node.
    from app.api.hls import cleanup_camera_cache
    for camera in list(node.cameras):
        cleanup_camera_cache(camera.camera_id)

    node_name = node.name
    db.delete(node)
    db.commit()

    write_audit(
        db,
        org_id=user.org_id,
        event="node_deleted",
        user_id=user.user_id,
        username=audit_label(user),
        details={"node_id": node_id, "name": node_name, "node_wiped": node_wiped},
        request=request,
    )

    return {"success": True, "deleted": node_id, "node_wiped": node_wiped}


@router.post("/{node_id}/rotate-key")
@limiter.limit("5/minute")
async def rotate_api_key(
    request: Request,
    node_id: str,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Rotate the API key for a node.
    The old key is immediately invalidated.
    CloudNode will be notified on next heartbeat.
    """
    node = db.query(CameraNode).filter_by(node_id=node_id, org_id=user.org_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    new_api_key = str(uuid_mod.uuid4())
    node.api_key_hash = hashlib.sha256(new_api_key.encode()).hexdigest()
    node.key_rotated_at = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    db.commit()

    write_audit(
        db,
        org_id=user.org_id,
        event="node_key_rotated",
        user_id=user.user_id,
        username=audit_label(user),
        details={"node_id": node_id, "name": node.name},
        request=request,
    )

    return {
        "success": True,
        "node_id": node_id,
        "api_key": new_api_key,
        "key_rotated_at": node.key_rotated_at.isoformat(),
        "warning": "Store this API key securely. It cannot be retrieved again. Update your CloudNode config immediately.",
    }
