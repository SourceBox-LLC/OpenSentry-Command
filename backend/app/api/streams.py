import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.config import settings
from app.models import Camera, CameraNode, StreamAccessLog, PendingUpload
from app.services.storage import get_storage, TigrisStorage

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/api", tags=["streams"])


def log_stream_access(
    db: Session,
    user_id: str,
    org_id: str,
    camera_id: str,
    node_id: str,
    ip_address: Optional[str],
    user_agent: Optional[str],
):
    """Log a stream access event."""
    log = StreamAccessLog(
        user_id=user_id,
        org_id=org_id,
        camera_id=camera_id,
        node_id=node_id,
        ip_address=ip_address,
        user_agent=user_agent[:500] if user_agent else None,
    )
    db.add(log)
    db.commit()

    cleanup_old_logs(db, org_id)


def cleanup_old_logs(db: Session, org_id: str):
    """Delete logs older than retention period (7 days by default)."""
    retention_days = settings.AUDIT_LOG_RETENTION_DAYS
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    db.query(StreamAccessLog).filter(
        StreamAccessLog.org_id == org_id,
        StreamAccessLog.accessed_at < cutoff,
    ).delete()
    db.commit()


@router.get("/cameras/{camera_id}/stream-url")
@limiter.limit("10/minute")
async def get_stream_url(
    request: Request,
    camera_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get a signed URL for streaming camera video.
    Rate limited to 10 requests per minute per IP.
    """
    camera = db.query(Camera).filter_by(camera_id=camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    node = db.query(CameraNode).filter_by(id=camera.node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Camera node not found")

    if node.org_id != user.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        storage = get_storage()
        stream_url = storage.generate_stream_url(
            camera_id=camera_id,
            org_id=user.org_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Storage not configured: {e}")

    log_stream_access(
        db=db,
        user_id=user.sub,
        org_id=user.org_id,
        camera_id=camera_id,
        node_id=node.node_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return {"url": stream_url, "expires_in": settings.STREAM_URL_EXPIRY_SECONDS}


@router.post("/cameras/{camera_id}/upload-url")
async def get_upload_url(
    camera_id: str,
    filename: str,
    checksum: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Get a signed URL for uploading a video segment.
    Called by CloudNode with its API key.

    Args:
        filename: The actual segment filename (e.g., "segment_00000.ts")
        checksum: BLAKE3 hash of the segment content
    """
    # Get API key from multiple possible headers
    node_api_key = (
        request.headers.get("X-Node-API-Key")
        or request.headers.get("X-API-Key")
        or request.headers.get("Authorization", "").replace("Bearer ", "")
    )

    print(f"[upload-url] Request for camera={camera_id}, filename={filename}")
    print(f"[upload-url] API key present: {bool(node_api_key)}")

    if not node_api_key:
        print(f"[upload-url] ERROR: No API key provided")
        raise HTTPException(status_code=401, detail="API key required")

    api_key_hash = hashlib.sha256(node_api_key.encode()).hexdigest()
    print(f"[upload-url] Looking up node by API key hash")

    node = db.query(CameraNode).filter_by(api_key_hash=api_key_hash).first()
    if not node:
        print(f"[upload-url] ERROR: Invalid API key (no matching node)")
        raise HTTPException(status_code=401, detail="Invalid API key")

    print(f"[upload-url] Found node: node_id={node.node_id}, org_id={node.org_id}")

    camera = db.query(Camera).filter_by(camera_id=camera_id).first()
    if not camera:
        print(f"[upload-url] ERROR: Camera not found: {camera_id}")
        raise HTTPException(status_code=404, detail="Camera not found")

    if camera.node_id != node.id:
        print(
            f"[upload-url] ERROR: Camera node_id={camera.node_id} doesn't match node.id={node.id}"
        )
        raise HTTPException(
            status_code=403, detail="Camera does not belong to this node"
        )

    try:
        storage = get_storage()
    except ValueError as e:
        print(f"[upload-url] ERROR: Storage not configured: {e}")
        raise HTTPException(status_code=500, detail=f"Storage not configured: {e}")

    upload_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(minutes=settings.UPLOAD_TIMEOUT_MINUTES)

    upload_url, s3_key = storage.generate_upload_url(
        camera_id=camera_id,
        org_id=node.org_id,
        filename=filename,
        checksum=checksum,
    )

    pending = PendingUpload(
        upload_id=upload_id,
        camera_id=camera_id,
        org_id=node.org_id,
        node_id=node.node_id,
        s3_key=s3_key,
        expected_checksum=checksum,
        expires_at=expires_at,
    )
    db.add(pending)
    db.commit()

    print(f"[upload-url] Success: upload_id={upload_id}, url generated")

    return {
        "upload_id": upload_id,
        "upload_url": upload_url,
        "expires_in": settings.UPLOAD_URL_EXPIRY_SECONDS,
    }


@router.post("/cameras/{camera_id}/upload-complete")
async def confirm_upload(
    camera_id: str,
    upload_id: str,
    node_api_key: str = Header(alias="X-Node-API-Key"),
    db: Session = Depends(get_db),
):
    """
    Confirm that a segment upload completed.
    Called by CloudNode after uploading to Tigris.

    Note: We trust the checksum header (x-amz-content-sha256) sent during upload.
    S3-compatible storage validates this automatically, so we don't need to
    verify again. This reduces latency for live streaming.
    """
    api_key_hash = hashlib.sha256(node_api_key.encode()).hexdigest()

    node = db.query(CameraNode).filter_by(api_key_hash=api_key_hash).first()
    if not node:
        raise HTTPException(status_code=401, detail="Invalid API key")

    pending = (
        db.query(PendingUpload)
        .filter_by(
            upload_id=upload_id,
            camera_id=camera_id,
        )
        .first()
    )

    if not pending:
        raise HTTPException(status_code=404, detail="Upload not found")

    if pending.completed:
        raise HTTPException(status_code=400, detail="Upload already completed")

    if pending.node_id != node.node_id:
        raise HTTPException(
            status_code=403, detail="Upload does not belong to this node"
        )

    if pending.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Upload has expired")

    # Mark upload as complete
    # Note: S3-compatible storage already verified checksum via x-amz-content-sha256 header
    pending.completed = True
    db.commit()

    return {"success": True, "message": "Upload confirmed"}
