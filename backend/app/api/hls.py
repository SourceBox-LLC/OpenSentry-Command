import asyncio
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
from app.services.storage import get_storage

router = APIRouter(prefix="/api/cameras/{camera_id}", tags=["streaming"])
logger = logging.getLogger(__name__)

# Pre-compiled regex patterns — avoids recompilation on every request.
_RE_SEGMENT = re.compile(r"^(segment_\d+\.ts)$", re.MULTILINE)
_RE_CODECS = re.compile(r"^#EXT-X-CODECS:.*$", re.MULTILINE)
_RE_VERSION = re.compile(r"(#EXT-X-VERSION:\d+)")

# ── Rewritten playlist cache ──────────────────────────────────────────
# Stores the fully-rewritten playlist (with presigned segment URLs and
# codec headers) so that browser polls are served instantly — no Tigris
# fetch and no presigned-URL crypto on every request.
#
# The cache is populated in update_hls_playlist() when the CloudNode
# pushes a new playlist. Browser GET requests just serve the cached
# string. If no cache exists yet (first request before any push), we
# fall back to fetching from Tigris and rewriting on the fly.
#
# {camera_id: (rewritten_playlist_text, timestamp)}
_playlist_cache: dict[str, tuple[str, float]] = {}
# Presigned URLs are valid for 15 minutes (900s). Refresh the cached
# playlist periodically even if the CloudNode hasn't pushed an update,
# so that segment URLs never expire while still in the playlist.
_PLAYLIST_CACHE_MAX_AGE = 300.0  # 5 minutes — well within 15-min URL expiry
_CACHE_MAX_CAMERAS = 500  # Evict oldest entries above this limit

# Track playlist update count per camera to trigger periodic Tigris cleanup.
# Old segments pile up on Tigris since batch uploads have no confirm step.
_playlist_update_count: dict[str, int] = {}

# ── Stream access logging (rate-limited) ─────────────────────────────
# HLS.js polls the playlist every ~1s. Logging every request would flood
# the DB.  Instead, we log at most once per user+camera per 5 minutes,
# which captures distinct "viewing sessions" without noise.
#
# {(user_id, camera_id): monotonic_timestamp_of_last_log}
_ACCESS_LOG_INTERVAL = 300.0  # 5 minutes
_last_access_logged: dict[tuple[str, str], float] = {}
_ACCESS_LOG_MAX_ENTRIES = 10000  # Evict stale entries above this limit


def _evict_caches():
    """Evict stale entries from module-level caches to prevent unbounded growth."""
    now = time.monotonic()

    # Evict expired playlist caches
    if len(_playlist_cache) > _CACHE_MAX_CAMERAS:
        # Sort by timestamp, keep newest
        sorted_entries = sorted(_playlist_cache.items(), key=lambda x: x[1][1])
        for camera_id, _ in sorted_entries[:len(sorted_entries) - _CACHE_MAX_CAMERAS]:
            del _playlist_cache[camera_id]
            _playlist_update_count.pop(camera_id, None)

    # Evict stale access log entries (older than 2x the log interval)
    if len(_last_access_logged) > _ACCESS_LOG_MAX_ENTRIES:
        cutoff = now - (_ACCESS_LOG_INTERVAL * 2)
        stale_keys = [k for k, ts in _last_access_logged.items() if ts < cutoff]
        for k in stale_keys:
            del _last_access_logged[k]


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
    org_id: str,
    video_codec: str = "avc1.42e01e",
    audio_codec: str = "mp4a.40.2",
) -> str:
    """
    Rewrite raw HLS playlist: replace segment filenames with presigned
    Tigris GET URLs and inject codec headers. Pure function — no I/O
    except presigned URL generation (local HMAC, no network call).
    """
    storage = get_storage()

    def _make_presigned(match):
        filename = match.group(1)
        return storage.generate_segment_url(camera_id, org_id, filename)

    playlist_text = _RE_SEGMENT.sub(_make_presigned, raw_playlist)

    # Remove any existing CODECS line then inject after VERSION.
    playlist_text = _RE_CODECS.sub("", playlist_text)
    playlist_text = _RE_VERSION.sub(
        rf"\1\n#EXT-X-CODECS:{video_codec},{audio_codec}",
        playlist_text,
    )

    return playlist_text


@router.get("/stream.m3u8")
async def get_hls_playlist(
    request: Request,
    camera_id: str,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get HLS playlist for a camera stream.
    Returns the pre-rewritten playlist from cache. The cache is populated
    when the CloudNode pushes a playlist update, so this endpoint does
    zero Tigris I/O and zero presigned-URL generation in the hot path.
    """
    camera = db.query(Camera).filter_by(camera_id=camera_id, org_id=user.org_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    node = db.query(CameraNode).filter_by(id=camera.node_id, org_id=user.org_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Camera node not found")

    # Log stream access (rate-limited — at most once per user+camera per 5 min)
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

    try:
        # Fast path: serve from cache (populated by update_hls_playlist).
        now = time.monotonic()
        cached = _playlist_cache.get(camera_id)
        if cached and (now - cached[1]) < _PLAYLIST_CACHE_MAX_AGE:
            return Response(
                content=cached[0],
                media_type="application/vnd.apple.mpegurl",
                headers=headers,
            )

        # Slow path: cache miss (first request or cache expired).
        # Fetch from Tigris and rewrite. boto3 is blocking, so run
        # in a thread to avoid freezing the async event loop.
        storage = get_storage()
        playlist_data = await asyncio.to_thread(
            storage.get_playlist,
            camera_id=camera_id,
            org_id=user.org_id,
        )

        raw_playlist = playlist_data.decode("utf-8")
        video_codec = camera.video_codec or (node.video_codec if node else None) or "avc1.42e01e"
        audio_codec = camera.audio_codec or (node.audio_codec if node else None) or "mp4a.40.2"

        playlist_text = _rewrite_playlist(
            raw_playlist, camera_id, user.org_id, video_codec, audio_codec
        )

        _playlist_cache[camera_id] = (playlist_text, now)

        return Response(
            content=playlist_text,
            media_type="application/vnd.apple.mpegurl",
            headers=headers,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Stream not started yet")
    except ValueError:
        logger.error("Storage not configured for playlist GET camera=%s", camera_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Storage service unavailable")
    except Exception:
        logger.error("Failed to get playlist for camera=%s", camera_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load stream")


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
    camera = db.query(Camera).filter_by(camera_id=camera_id, org_id=user.org_id).first()
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    node = db.query(CameraNode).filter_by(id=camera.node_id, org_id=user.org_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Camera node not found")

    if not filename.endswith(".ts") or not filename.startswith("segment_"):
        raise HTTPException(status_code=400, detail="Invalid segment filename")

    try:
        storage = get_storage()
        segment_data = await asyncio.to_thread(
            storage.get_segment,
            camera_id=camera_id,
            org_id=user.org_id,
            filename=filename,
        )

        return Response(
            content=segment_data,
            media_type="video/mp2t",
            headers={
                "Cache-Control": "public, max-age=3600",
            },
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Segment not found")
    except ValueError:
        logger.error("Storage not configured for segment GET camera=%s", camera_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Storage service unavailable")
    except Exception:
        logger.error("Failed to get segment %s for camera=%s", filename, camera_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load segment")


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

    This is the HOT PATH for streaming efficiency: we pre-compute the
    rewritten playlist (with presigned segment URLs) here so that
    browser GET requests serve the cached result instantly — zero
    Tigris I/O and zero crypto per browser poll.
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

    try:
        storage = get_storage()
        await asyncio.to_thread(
            storage.save_playlist,
            camera_id=camera_id,
            org_id=node.org_id,
            content=playlist_content,
        )

        # Pre-compute the rewritten playlist with presigned segment URLs
        # and cache it. Browser polls will serve this instantly.
        video_codec = camera.video_codec or (node.video_codec if node else None) or "avc1.42e01e"
        audio_codec = camera.audio_codec or (node.audio_codec if node else None) or "mp4a.40.2"

        rewritten = _rewrite_playlist(
            playlist_content, camera_id, node.org_id, video_codec, audio_codec
        )
        _playlist_cache[camera_id] = (rewritten, time.monotonic())

        # Periodically clean up old segments on Tigris and evict stale caches.
        count = _playlist_update_count.get(camera_id, 0) + 1
        _playlist_update_count[camera_id] = count
        if count % settings.CLEANUP_INTERVAL == 0:
            _evict_caches()
            asyncio.ensure_future(
                _cleanup_old_segments(node.org_id, camera_id)
            )

        return {"success": True, "message": "Playlist updated"}
    except ValueError:
        logger.error("Storage not configured for playlist POST camera=%s", camera_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Storage service unavailable")
    except Exception:
        logger.error("Failed to save playlist for camera=%s", camera_id, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save playlist")


async def _cleanup_old_segments(org_id: str, camera_id: str):
    """Delete old segments from Tigris in the background."""
    try:
        storage = get_storage()
        await asyncio.to_thread(
            storage.cleanup_old_segments,
            org_id=org_id,
            camera_id=camera_id,
            keep_count=settings.SEGMENT_RETENTION_COUNT,
        )
        logger.debug("Cleaned old segments for camera %s", camera_id)
    except Exception as e:
        logger.warning("Cleanup failed for camera %s: %s", camera_id, e)
