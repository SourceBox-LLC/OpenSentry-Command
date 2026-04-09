import hashlib
import logging
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import AuthUser, require_admin, get_current_user
from app.core.limiter import limiter
from app.core.plans import get_plan_limits, get_plan_limits_for_org, get_plan_display_name
from app.models.models import CameraNode, Camera
from app.schemas.schemas import NodeRegister, NodeHeartbeat, CameraReport, NodeCreate
from app.services.storage import get_storage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


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
    api_key = request.headers.get("X-API-Key")
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
    api_key = request.headers.get("X-API-Key") or request.headers.get(
        "Authorization", ""
    ).replace("Bearer ", "")

    logger.debug("API key present: %s", bool(api_key))

    if not api_key:
        logger.warning("Registration rejected: no API key provided")
        raise HTTPException(status_code=401, detail="API key required")

    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    existing_node = db.query(CameraNode).filter_by(node_id=data.node_id).first()

    if existing_node:
        logger.info("Found existing node id=%s, org=%s", existing_node.id, existing_node.org_id)
        if existing_node.api_key_hash != api_key_hash:
            logger.warning("Registration rejected: API key mismatch for node %s", data.node_id)
            raise HTTPException(status_code=403, detail="Invalid API key for this node")

        existing_node.hostname = data.hostname or existing_node.hostname
        existing_node.local_ip = data.local_ip or existing_node.local_ip
        existing_node.http_port = data.http_port or existing_node.http_port
        existing_node.status = "online"
        existing_node.last_seen = datetime.now(tz=timezone.utc).replace(tzinfo=None)

        if data.video_codec:
            existing_node.video_codec = data.video_codec
            existing_node.audio_codec = data.audio_codec
            existing_node.codec_detected_at = datetime.now(tz=timezone.utc).replace(tzinfo=None)

        # Enforce camera cap: count existing org cameras vs plan limit
        org_id = existing_node.org_id
        limits = get_plan_limits_for_org(db, org_id)
        current_cameras = db.query(Camera).filter_by(org_id=org_id).count()

        # Map device_path to camera_id for response
        camera_mapping = {}
        new_camera_count = 0

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
                    existing_cam.video_codec = data.video_codec
                    existing_cam.audio_codec = data.audio_codec
            else:
                # Check camera cap before creating
                if current_cameras + new_camera_count >= limits["max_cameras"]:
                    plan_name = get_plan_display_name(limits.get("_plan", "free_org"))
                    logger.warning(
                        "Camera limit reached for org %s (%d/%d on %s plan), skipping camera %s",
                        org_id, current_cameras + new_camera_count, limits["max_cameras"], plan_name, camera_id,
                    )
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
                    video_codec=data.video_codec,
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
                try:
                    storage = get_storage()
                    storage.delete_camera_storage(
                        existing_node.org_id, stale_cam.camera_id
                    )
                except Exception as e:
                    logger.warning("Could not clean Tigris storage for %s: %s", stale_cam.camera_id, e)
                db.delete(stale_cam)

        db.commit()
        logger.info("Node %s re-registered successfully with %d cameras", data.node_id, len(camera_mapping))

        return {
            "success": True,
            "node_id": existing_node.node_id,
            "node_secret": api_key,
            "status": "updated",
            "message": "Node re-registered successfully",
            "cameras": camera_mapping,
        }

    logger.warning("Registration failed: node_id=%s not found in database", data.node_id)
    raise HTTPException(
        status_code=404,
        detail="Node not found. Create this node in the dashboard first.",
    )


@router.post("/heartbeat")
async def node_heartbeat(
    request: Request,
    data: NodeHeartbeat,
    db: Session = Depends(get_db),
):
    logger.debug("Heartbeat received from node_id=%s", data.node_id)
    api_key = request.headers.get("X-API-Key") or request.headers.get(
        "Authorization", ""
    ).replace("Bearer ", "")

    if not api_key:
        logger.warning("Heartbeat rejected: no API key provided for node %s", data.node_id)
        raise HTTPException(status_code=401, detail="API key required")

    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    node = db.query(CameraNode).filter_by(node_id=data.node_id).first()

    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    if node.api_key_hash != api_key_hash:
        raise HTTPException(status_code=403, detail="Invalid API key")

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

    db.commit()

    return {"success": True, "timestamp": datetime.now(tz=timezone.utc).replace(tzinfo=None).isoformat()}


@router.get("")
async def list_nodes(
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    nodes = db.query(CameraNode).filter_by(org_id=user.org_id).all()
    return [n.to_dict() for n in nodes]


@router.get("/plan")
async def get_plan_info(
    user: AuthUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the org's current plan, usage, and limits."""
    limits = get_plan_limits(user.plan)
    current_nodes = db.query(CameraNode).filter_by(org_id=user.org_id).count()
    current_cameras = db.query(Camera).filter_by(org_id=user.org_id).count()
    return {
        "plan": user.plan,
        "plan_name": get_plan_display_name(user.plan),
        "features": user.features,
        "limits": limits,
        "usage": {
            "nodes": current_nodes,
            "cameras": current_cameras,
        },
    }


@router.post("")
async def create_node(
    data: NodeCreate,
    user: AuthUser = Depends(require_admin),
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

    node_id = str(uuid.uuid4())[:8]
    api_key = str(uuid.uuid4())
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
async def delete_node(
    node_id: str,
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

    # Clean up Tigris storage for every camera on this node before deleting DB records.
    cameras_deleted = []
    try:
        storage = get_storage()
        for camera in list(node.cameras):
            count = storage.delete_camera_storage(user.org_id, camera.camera_id)
            cameras_deleted.append(
                {"camera_id": camera.camera_id, "objects_deleted": count}
            )
            logger.info("Deleted %d storage objects for camera %s", count, camera.camera_id)
    except Exception as e:
        # Don't block the delete if storage cleanup fails — log and continue.
        logger.warning("Storage cleanup failed for node %s: %s", node_id, e)

    db.delete(node)
    db.commit()

    return {"success": True, "deleted": node_id, "storage_cleaned": cameras_deleted, "node_wiped": node_wiped}


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

    new_api_key = str(uuid.uuid4())
    node.api_key_hash = hashlib.sha256(new_api_key.encode()).hexdigest()
    node.key_rotated_at = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    db.commit()

    return {
        "success": True,
        "node_id": node_id,
        "api_key": new_api_key,
        "key_rotated_at": node.key_rotated_at.isoformat(),
        "warning": "Store this API key securely. It cannot be retrieved again. Update your CloudNode config immediately.",
    }
