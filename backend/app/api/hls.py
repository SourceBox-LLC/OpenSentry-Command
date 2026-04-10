import hashlib
import re
import time
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import settings
from app.core.auth import get_current_user
from app.models import Camera, CameraNode, StreamAccessLog

router = APIRouter(prefix="/api/cameras/{camera_id}", tags=["streaming"])
logger = logging.getLogger(__name__)

# Pre-compiled regex patterns — avoids recompilation on every request.
_RE_SEGMENT = re.compile(r"^(segment_\d+\.ts)$", re.MULTILINE)
_RE_CODECS = re.compile(r"^#EXT-X-CODECS:.*$", re.MULTILINE)
_RE_VERSION = re.compile(r"(#EXT-X-VERSION:\d+)")
_RE_SEGMENT_FILENAME = re.compile(r"^segment_\d+\.ts$")

# ── Rewritten playlist cache ──────────────────────────────────────────
# Populated by POST /playlist (CloudNode push). Browser GET requests
# serve the cached string instantly — no I/O per poll.
#
# {camera_id: (rewritten_playlist_text, timestamp)}
_playlist_cache: dict[str, tuple[str, float]] = {}
_PLAYLIST_CACHE_MAX_AGE = 300.0  # 5 minutes
_CACHE_MAX_CAMERAS = 500

# ── In-memory segment cache ──────────────────────────────────────────
# CloudNode pushes segments via POST /push-segment. Browser fetches
# them via GET /segment/{filename}. No Tigris in the live path.
#
# {camera_id: {filename: (bytes_data, monotonic_timestamp)}}
_segment_cache: dict[str, dict[str, tuple[bytes, float]]] = {}

# Track playlist update count per camera (for legacy Tigris cleanup).
_playlist_update_count: dict[str, int] = {}

# ── Stream access logging (rate-limited) ─────────────────────────────
_ACCESS_LOG_INTERVAL = 300.0  # 5 minutes
_last_access_logged: dict[tuple[str, str], float] = {}
_ACCESS_LOG_MAX_ENTRIES = 10000


# ── Cache management ─────────────────────────────────────────────────

def cleanup_camera_cache(camera_id: str):
    """Remove all cached segments and playlist for a camera.
    Called when a camera or node is deleted."""
    _segment_cache.pop(camera_id, None)
    _playlist_cache.pop(camera_id, None)
    _playlist_update_count.pop(camera_id, None)


def _evict_segment_cache(camera_id: str):
    """Keep only the newest SEGMENT_CACHE_MAX_PER_CAMERA segments for a camera."""
    cam_cache = _segment_cache.get(camera_id)
    if not cam_cache or len(cam_cache) <= settings.SEGMENT_CACHE_MAX_PER_CAMERA:
        return
    # Sort by filename (monotonically increasing sequence numbers)
    sorted_keys = sorted(cam_cache.keys())
    to_remove = sorted_keys[: len(sorted_keys) - settings.SEGMENT_CACHE_MAX_PER_CAMERA]
    for key in to_remove:
        del cam_cache[key]


def _evict_stale_cameras():
    """Remove segment caches for cameras that haven't received data in 5+ minutes."""
    now = time.monotonic()
    cutoff = now - 300.0  # 5 minutes
    stale = []
    for camera_id, segments in _segment_cache.items():
        if not segments:
            stale.append(camera_id)
            continue
        newest_ts = max(ts for _, ts in segments.values())
        if newest_ts < cutoff:
            stale.append(camera_id)
    for camera_id in stale:
        del _segment_cache[camera_id]
        _playlist_cache.pop(camera_id, None)


def _evict_caches():
    """Evict stale entries from module-level caches to prevent unbounded growth."""
    now = time.monotonic()

    if len(_playlist_cache) > _CACHE_MAX_CAMERAS:
        sorted_entries = sorted(_playlist_cache.items(), key=lambda x: x[1][1])
        for camera_id, _ in sorted_entries[:len(sorted_entries) - _CACHE_MAX_CAMERAS]:
            del _playlist_cache[camera_id]
            _playlist_update_count.pop(camera_id, None)

    if len(_last_access_logged) > _ACCESS_LOG_MAX_ENTRIES:
        cutoff = now - (_ACCESS_LOG_INTERVAL * 2)
        stale_keys = [k for k, ts in _last_access_logged.items() if ts < cutoff]
        for k in stale_keys:
            del _last_access_logged[k]

    _evict_stale_cameras()


def _maybe_log_access(
    db: Session,
    user_id: str,
    user_email: str,
    org_id: str,
    camera_id: str,
    node_id: str,
    ip_address: str,
    user_agent: str,
) -> None:
    """Create a StreamAccessLog entry if enough time has passed."""
    now = time.monotonic()
    key = (user_id, camera_id)
    last = _last_access_logged.get(key, 0.0)
    if now - last < _ACCESS_LOG_INTERVAL:
        return

    _last_access_logged[key] = now

    try:
        from datetime import datetime, timezone
        log_entry = StreamAccessLog(
            user_id=user_id,
            user_email=user_email,
            org_id=org_id,
            camera_id=camera_id,
            node_id=node_id,
            ip_address=ip_address,
            user_agent=user_agent,
            accessed_at=datetime.now(tz=timezone.utc).replace(tzinfo=None),
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        logger.warning("Failed to log stream access: %s", e)
        db.rollback()


def _rewrite_playlist(
    raw_playlist: str,
    camera_id: str,
    video_codec: str = "avc1.42e01e",
    audio_codec: str = "mp4a.40.2",
) -> str:
    """
    Rewrite raw HLS playlist: replace bare segment filenames with
    relative proxy URLs (segment/<filename>) and inject codec headers.
    Pure string manipulation — no I/O, no Tigris, no presigned URLs.
    """
    # Prefix segment filenames with "segment/" so the browser resolves
    # them relative to the playlist URL → /api/cameras/{id}/segment/<file>
    playlist_text = _RE_SEGMENT.sub(r"segment/\1", raw_playlist)

    # Remove any existing CODECS line then inject after VERSION.
    playlist_text = _RE_CODECS.sub("", playlist_text)
    playlist_text = _RE_VERSION.sub(
        rf"\1\n#EXT-X-CODECS:{video_codec},{audio_codec}",
        playlist_text,
    )

    return playlist_text


# ── Endpoints ─────────────────────────────────────────────────────────

@router.get("/stream.m3u8")
async def get_hls_playlist(
    request: Request,
    camera_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get HLS playlist for a camera stream.
    Served from the in-memory cache populated by POST /playlist.
    """
    camera = db.query(Camera).filter_by(camera_id=camera_id, org_id=user.org_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    node = db.query(CameraNode).filter_by(id=camera.node_id, org_id=user.org_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Camera node not found")

    _maybe_log_access(
        db=db,
        user_id=user.user_id,
        user_email=user.email,
        org_id=user.org_id,
        camera_id=camera_id,
        node_id=str(node.id),
        ip_address=request.client.host if request.client else "unknown",
        user_agent=request.headers.get("user-agent", "")[:500],
    )

    headers = {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    }

    # Serve from cache (populated by POST /playlist from CloudNode).
    cached = _playlist_cache.get(camera_id)
    if cached and (time.monotonic() - cached[1]) < _PLAYLIST_CACHE_MAX_AGE:
        return Response(
            content=cached[0],
            media_type="application/vnd.apple.mpegurl",
            headers=headers,
        )

    # No cached playlist — CloudNode hasn't pushed one yet.
    raise HTTPException(status_code=404, detail="Stream not started yet")


@router.get("/segment/{filename}")
async def get_hls_segment(
    request: Request,
    camera_id: str,
    filename: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Serve an HLS segment from the in-memory cache."""
    camera = db.query(Camera).filter_by(camera_id=camera_id, org_id=user.org_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    if not _RE_SEGMENT_FILENAME.match(filename):
        raise HTTPException(status_code=400, detail="Invalid segment filename")

    cam_cache = _segment_cache.get(camera_id)
    if cam_cache:
        entry = cam_cache.get(filename)
        if entry:
            return Response(
                content=entry[0],
                media_type="video/mp2t",
                headers={"Cache-Control": "public, max-age=3600"},
            )

    raise HTTPException(status_code=404, detail="Segment not found")


@router.post("/push-segment")
async def push_segment(
    request: Request,
    camera_id: str,
    filename: str,
    db: Session = Depends(get_db),
):
    """
    Receive an HLS segment pushed by CloudNode.
    Stores in memory for the browser to fetch via GET /segment/{filename}.
    Replaces the old Tigris upload flow — no S3 involved.
    """
    node_api_key = request.headers.get("X-Node-API-Key")
    if not node_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    api_key_hash = hashlib.sha256(node_api_key.encode()).hexdigest()
    node = db.query(CameraNode).filter_by(api_key_hash=api_key_hash).first()
    if not node:
        raise HTTPException(status_code=401, detail="Invalid API key")

    camera = db.query(Camera).filter_by(camera_id=camera_id, node_id=node.id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    if not _RE_SEGMENT_FILENAME.match(filename):
        raise HTTPException(status_code=400, detail="Invalid segment filename")

    body = await request.body()
    if len(body) > settings.SEGMENT_PUSH_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Segment too large")

    # Cache the segment.
    if camera_id not in _segment_cache:
        _segment_cache[camera_id] = {}
    _segment_cache[camera_id][filename] = (body, time.monotonic())
    _evict_segment_cache(camera_id)

    return {"success": True, "cached_segments": len(_segment_cache[camera_id])}


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

    Rewrites segment filenames to relative proxy URLs and caches the
    result so browser GET requests are served instantly.
    """
    node_api_key = request.headers.get("X-Node-API-Key")
    if not node_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    api_key_hash = hashlib.sha256(node_api_key.encode()).hexdigest()
    node = db.query(CameraNode).filter_by(api_key_hash=api_key_hash).first()
    if not node:
        raise HTTPException(status_code=401, detail="Invalid API key")

    camera = db.query(Camera).filter_by(camera_id=camera_id, node_id=node.id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    try:
        playlist_content = (await request.body()).decode("utf-8")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid playlist content: {e}")

    # Pre-compute the rewritten playlist with proxy segment URLs
    # and cache it. Browser polls will serve this instantly.
    video_codec = camera.video_codec or (node.video_codec if node else None) or "avc1.42e01e"
    audio_codec = camera.audio_codec or (node.audio_codec if node else None) or "mp4a.40.2"

    rewritten = _rewrite_playlist(
        playlist_content, camera_id, video_codec, audio_codec
    )
    _playlist_cache[camera_id] = (rewritten, time.monotonic())

    # Periodic cache eviction.
    count = _playlist_update_count.get(camera_id, 0) + 1
    _playlist_update_count[camera_id] = count
    if count % settings.CLEANUP_INTERVAL == 0:
        _evict_caches()

    return {"success": True, "message": "Playlist updated"}
