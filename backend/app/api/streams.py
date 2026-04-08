import hashlib
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.models import Camera, CameraNode
from app.services.storage import get_storage

router = APIRouter(prefix="/api", tags=["streams"])
logger = logging.getLogger(__name__)

# ─── Batch upload URLs ────────────────────────────────────────────────
# The old per-segment flow required 3 HTTP round-trips per 2-second
# segment (get-url, PUT, confirm). With network variance, total
# processing time could exceed segment duration, causing the pipeline
# to fall behind and never recover ("buffer wall").
#
# The batch endpoint returns N presigned URLs in a single request.
# The CloudNode uploads segments directly to Tigris without any
# per-segment backend calls. One request covers ~60s of streaming.


@router.post("/cameras/{camera_id}/upload-urls")
async def get_batch_upload_urls(
    camera_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Get a batch of presigned upload URLs for streaming segments.
    Called once by CloudNode, covers ~60 seconds of streaming.
    CloudNode requests a new batch when running low.

    Body JSON: { "start_sequence": 0, "count": 30 }
    """
    node_api_key = (
        request.headers.get("X-Node-API-Key")
        or request.headers.get("X-API-Key")
        or request.headers.get("Authorization", "").replace("Bearer ", "")
    )

    if not node_api_key:
        raise HTTPException(status_code=401, detail="API key required")

    api_key_hash = hashlib.sha256(node_api_key.encode()).hexdigest()
    node = db.query(CameraNode).filter_by(api_key_hash=api_key_hash).first()
    if not node:
        raise HTTPException(status_code=401, detail="Invalid API key")

    camera = db.query(Camera).filter_by(camera_id=camera_id, node_id=node.id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    try:
        body = await request.json()
    except Exception:
        body = {}

    start_seq = body.get("start_sequence", 0)
    count = min(body.get("count", 30), 100)  # Cap at 100

    try:
        storage = get_storage()
    except ValueError:
        logger.error("Storage not configured for upload-urls camera=%s", camera_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Storage service unavailable")

    # Generate presigned URLs for segments and the playlist
    urls = []
    for i in range(count):
        seq = start_seq + i
        filename = f"segment_{seq:05d}.ts"
        upload_url, s3_key = storage.generate_upload_url(
            camera_id=camera_id,
            org_id=node.org_id,
            filename=filename,
        )
        urls.append({
            "sequence": seq,
            "filename": filename,
            "upload_url": upload_url,
        })

    # Also generate a presigned URL for the playlist
    playlist_url, _ = storage.generate_upload_url(
        camera_id=camera_id,
        org_id=node.org_id,
        filename="stream.m3u8",
    )

    return {
        "urls": urls,
        "playlist_upload_url": playlist_url,
        "expires_in": settings.UPLOAD_URL_EXPIRY_SECONDS,
    }
