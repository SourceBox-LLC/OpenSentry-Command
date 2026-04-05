import hashlib
import re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models import Camera, CameraNode
from app.services.storage import get_storage

router = APIRouter(prefix="/api/cameras/{camera_id}", tags=["streaming"])


@router.get("/stream.m3u8")
async def get_hls_playlist(
    request: Request,
    camera_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get HLS playlist for a camera stream.
    Returns the playlist from storage with segment URLs rewritten to
    presigned Tigris GET URLs so the browser fetches segments directly
    from object storage — no proxy hop through this backend.
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
        playlist_data = storage.get_playlist(
            camera_id=camera_id,
            org_id=user.org_id,
        )

        playlist_text = playlist_data.decode("utf-8")

        # Rewrite segment filenames to presigned Tigris GET URLs.
        # Segments are fetched directly from Tigris — no proxy hop through the backend.
        def _make_presigned(match):
            filename = match.group(1)
            return storage.generate_segment_url(camera_id, user.org_id, filename)

        playlist_text = re.sub(
            r"^(segment_\d+\.ts)$",
            _make_presigned,
            playlist_text,
            flags=re.MULTILINE,
        )

        # Use camera codec if detected, fall back to node codec, then defaults.
        video_codec = camera.video_codec or node.video_codec or "avc1.42e01e"
        audio_codec = camera.audio_codec or node.audio_codec or "mp4a.40.2"

        # Remove any existing CODECS line then inject after VERSION.
        playlist_text = re.sub(r"^#EXT-X-CODECS:.*$", "", playlist_text, flags=re.MULTILINE)
        playlist_text = re.sub(
            r"(#EXT-X-VERSION:\d+)",
            rf"\1\n#EXT-X-CODECS:{video_codec},{audio_codec}",
            playlist_text,
        )

        return Response(
            content=playlist_text,
            media_type="application/vnd.apple.mpegurl",
            headers={
                "Cache-Control": "no-cache",
                "Access-Control-Allow-Origin": "*",
            },
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Stream not started yet")
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Storage not configured: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get playlist: {e}")


@router.get("/segment/{filename}")
async def get_hls_segment(
    request: Request,
    camera_id: str,
    filename: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Fallback segment endpoint — proxies a segment from Tigris.
    Not used by the primary playlist flow (which issues presigned URLs),
    but kept for direct segment access if needed.
    """
    camera = db.query(Camera).filter_by(camera_id=camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    node = db.query(CameraNode).filter_by(id=camera.node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Camera node not found")

    if node.org_id != user.org_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if not filename.endswith(".ts") or not filename.startswith("segment_"):
        raise HTTPException(status_code=400, detail="Invalid segment filename")

    try:
        storage = get_storage()
        segment_data = storage.get_segment(
            camera_id=camera_id,
            org_id=user.org_id,
            filename=filename,
        )

        return Response(
            content=segment_data,
            media_type="video/mp2t",
            headers={
                "Cache-Control": "public, max-age=3600",
                "Access-Control-Allow-Origin": "*",
            },
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Segment not found")
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Storage not configured: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get segment: {e}")


@router.post("/playlist")
async def update_hls_playlist(
    request: Request,
    camera_id: str,
    db: Session = Depends(get_db),
):
    """
    Update the HLS playlist for a camera.
    Called by CloudNode when new segments are generated.
    Expects playlist content in request body (text/plain).
    """
    node_api_key = request.headers.get("X-Node-API-Key")
    if not node_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    api_key_hash = hashlib.sha256(node_api_key.encode()).hexdigest()

    node = db.query(CameraNode).filter_by(api_key_hash=api_key_hash).first()
    if not node:
        raise HTTPException(status_code=401, detail="Invalid API key")

    camera = db.query(Camera).filter_by(camera_id=camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    if camera.node_id != node.id:
        raise HTTPException(
            status_code=403, detail="Camera does not belong to this node"
        )

    try:
        playlist_content = (await request.body()).decode("utf-8")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid playlist content: {e}")

    try:
        storage = get_storage()
        storage.save_playlist(
            camera_id=camera_id,
            org_id=node.org_id,
            content=playlist_content,
        )
        return {"success": True, "message": "Playlist updated"}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Storage not configured: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save playlist: {e}")


@router.post("/codec")
async def update_camera_codec(
    request: Request,
    camera_id: str,
    db: Session = Depends(get_db),
):
    """
    Update codec info for a camera stream.
    Called by CloudNode after detecting codec from the first uploaded segment.
    """
    node_api_key = request.headers.get("X-Node-API-Key")
    if not node_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    api_key_hash = hashlib.sha256(node_api_key.encode()).hexdigest()

    node = db.query(CameraNode).filter_by(api_key_hash=api_key_hash).first()
    if not node:
        raise HTTPException(status_code=401, detail="Invalid API key")

    camera = db.query(Camera).filter_by(camera_id=camera_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    if camera.node_id != node.id:
        raise HTTPException(status_code=403, detail="Camera does not belong to this node")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    video_codec = body.get("video_codec")
    audio_codec = body.get("audio_codec")

    if video_codec:
        camera.video_codec = video_codec
        camera.audio_codec = audio_codec
        camera.codec_detected_at = datetime.utcnow()
        db.commit()

    return {"success": True}
