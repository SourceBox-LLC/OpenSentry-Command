import hashlib
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import AuthUser, require_admin
from app.models.models import CameraNode, Camera
from app.schemas.schemas import NodeRegister, NodeHeartbeat, CameraReport, NodeCreate


router = APIRouter(prefix="/api/nodes", tags=["nodes"])


@router.post("/register")
async def register_node(
    request: Request,
    data: NodeRegister,
    db: Session = Depends(get_db),
):
    print(f"[register] Registration attempt from node_id={data.node_id}")
    api_key = request.headers.get("X-API-Key") or request.headers.get(
        "Authorization", ""
    ).replace("Bearer ", "")

    print(f"[register] API key present: {bool(api_key)}")

    if not api_key:
        print(f"[register] ERROR: No API key provided")
        raise HTTPException(status_code=401, detail="API key required")

    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    existing_node = db.query(CameraNode).filter_by(node_id=data.node_id).first()

    if existing_node:
        print(
            f"[register] Found existing node with id={existing_node.id}, org_id={existing_node.org_id}"
        )
        if existing_node.api_key_hash != api_key_hash:
            print(f"[register] ERROR: API key mismatch for existing node")
            raise HTTPException(status_code=403, detail="Invalid API key for this node")

        existing_node.hostname = data.hostname or existing_node.hostname
        existing_node.local_ip = data.local_ip or existing_node.local_ip
        existing_node.http_port = data.http_port or existing_node.http_port
        existing_node.status = "online"
        existing_node.last_seen = datetime.utcnow()

        # Map device_path to camera_id for response
        camera_mapping = {}

        for cam_data in data.cameras or []:
            # Generate camera_id from node_id and device_path
            device_path = cam_data.device_path or cam_data.camera_id or "unknown"
            # Sanitize device_path for use as camera_id
            sanitized_device = (
                device_path.replace("/", "_").replace("\\", "_").strip("_")
            )
            camera_id = f"{data.node_id}_{sanitized_device}"

            print(
                f"[register] Processing camera: device_path={device_path} -> camera_id={camera_id}"
            )

            camera_mapping[device_path] = camera_id

            existing_cam = db.query(Camera).filter_by(camera_id=camera_id).first()
            if existing_cam:
                print(f"[register] Updating existing camera {camera_id}")
                existing_cam.name = cam_data.name or existing_cam.name
                existing_cam.last_seen = datetime.utcnow()
                existing_cam.status = "online"
            else:
                print(f"[register] Creating new camera {camera_id}")
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
                    last_seen=datetime.utcnow(),
                )
                db.add(new_cam)

        db.commit()
        print(f"[register] Node re-registered successfully. Cameras: {camera_mapping}")

        return {
            "success": True,
            "node_id": existing_node.node_id,
            "node_secret": api_key,
            "status": "updated",
            "message": "Node re-registered successfully",
            "cameras": camera_mapping,
        }

    print(f"[register] ERROR: Node not found in database")
    return {
        "success": False,
        "status": "pending",
        "node_secret": "",
        "message": "Node not found. Please register this node in the dashboard first.",
    }


@router.post("/heartbeat")
async def node_heartbeat(
    request: Request,
    data: NodeHeartbeat,
    db: Session = Depends(get_db),
):
    print(f"[heartbeat] Received heartbeat from node_id={data.node_id}")
    api_key = request.headers.get("X-API-Key") or request.headers.get(
        "Authorization", ""
    ).replace("Bearer ", "")

    print(f"[heartbeat] API key header present: {bool(api_key)}")

    if not api_key:
        print(f"[heartbeat] ERROR: No API key provided")
        raise HTTPException(status_code=401, detail="API key required")

    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    print(f"[heartbeat] Looking up node with node_id={data.node_id}")

    node = db.query(CameraNode).filter_by(node_id=data.node_id).first()

    if not node:
        print(f"[heartbeat] ERROR: Node not found in database")
        print(
            f"[heartbeat] Available nodes: {[(n.node_id, n.id) for n in db.query(CameraNode).all()]}"
        )
        raise HTTPException(status_code=404, detail="Node not found")

    if node.api_key_hash != api_key_hash:
        print(f"[heartbeat] ERROR: API key mismatch")
        raise HTTPException(status_code=403, detail="Invalid API key")

    node.status = "online"
    node.last_seen = datetime.utcnow()
    node.local_ip = data.local_ip or node.local_ip

    for cam_status in data.cameras or []:
        cam = db.query(Camera).filter_by(camera_id=cam_status.camera_id).first()
        if cam:
            cam.status = cam_status.status
            cam.last_seen = datetime.utcnow()

    db.commit()
    print(f"[heartbeat] Heartbeat successful for node {data.node_id}")

    return {"success": True, "timestamp": datetime.utcnow().isoformat()}


@router.get("")
async def list_nodes(
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    nodes = db.query(CameraNode).filter_by(org_id=user.org_id).all()
    return [n.to_dict() for n in nodes]


@router.post("")
async def create_node(
    data: NodeCreate,
    user: AuthUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    print(
        f"[nodes] create_node called: name={data.name}, org_id={user.org_id}, user_id={user.user_id}"
    )

    node_id = str(uuid.uuid4())[:8]
    api_key = str(uuid.uuid4())
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    print(f"[nodes] Generated node_id={node_id}")

    node = CameraNode(
        node_id=node_id,
        org_id=user.org_id,
        name=data.name or f"Node-{node_id}",
        api_key_hash=api_key_hash,
        status="pending",
    )
    db.add(node)
    db.commit()

    print(f"[nodes] Node saved to database: node_id={node_id}, name={node.name}")

    response_data = {
        "success": True,
        "node_id": node_id,
        "name": node.name,
        "api_key": api_key,
        "warning": "Store this API key securely. It cannot be retrieved again.",
    }
    print(f"[nodes] Returning response: {response_data}")

    return response_data


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

    db.delete(node)
    db.commit()

    return {"success": True, "deleted": node_id}


@router.post("/{node_id}/rotate-key")
async def rotate_api_key(
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
    node.key_rotated_at = datetime.utcnow()
    db.commit()

    return {
        "success": True,
        "node_id": node_id,
        "api_key": new_api_key,
        "key_rotated_at": node.key_rotated_at.isoformat(),
        "warning": "Store this API key securely. It cannot be retrieved again. Update your CloudNode config immediately.",
    }
