"""
Tests for the live-video proxy path — the backend-cached HLS pipeline.

Covers:

- Segment roundtrip: a segment pushed by the owning CloudNode over
  ``POST /push-segment`` is byte-exact on a subsequent
  ``GET /segment/<filename>`` — the cache never corrupts the payload.
- Playlist rewriting: raw playlist text pushed by the CloudNode is
  served back with segment filenames proxied through this backend
  (``segment/segment_00001.ts``) — no absolute URLs leak through.
- Codec stripping: ``#EXT-X-CODECS`` lines are removed from media
  playlists since they're only valid in master playlists and break
  hls.js parsing.
- Cache eviction bounds: pushing more than
  ``SEGMENT_CACHE_MAX_PER_CAMERA`` segments drops the oldest.
- ``stream.m3u8`` returns 404 when no playlist has ever been pushed.
- ``cleanup_camera_cache`` removes both segments and playlist for a
  camera (used by delete/cleanup paths).
"""

import hashlib
import uuid

import pytest

from app.models.models import Camera, CameraNode


# ── Helpers ───────────────────────────────────────────────────────────


def _seed_node_with_camera(db, *, org_id="org_test123"):
    """Create one node+camera and return ``(raw_api_key, camera_id)``.

    We seed the hash (not the raw key) on the node row, same as production
    — so ``X-Node-API-Key: <raw>`` authenticates against it.
    """
    raw_key = "raw-key-" + uuid.uuid4().hex
    node = CameraNode(
        node_id="node_hls_" + uuid.uuid4().hex[:8],
        org_id=org_id,
        api_key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
        name="HlsTestNode",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    cam_id = "cam_hls_" + uuid.uuid4().hex[:8]
    db.add(
        Camera(
            camera_id=cam_id,
            org_id=org_id,
            node_id=node.id,
            name="HlsTestCam",
            video_codec="avc1.42e01e",
            audio_codec="mp4a.40.2",
        )
    )
    db.commit()
    return raw_key, cam_id


# ── Segment roundtrip ────────────────────────────────────────────────


def test_segment_roundtrip_bytes_match(admin_client, unauthenticated_client, db):
    """Push a segment with the owning node key; fetch it back as an
    authenticated user.  The payload must survive the cache unchanged —
    this is the contract MSE decoders rely on."""
    from app.api.hls import _segment_cache

    raw_key, cam_id = _seed_node_with_camera(db)
    # A realistic-ish TS sync byte payload so we know nothing is
    # reinterpreting bytes as text along the way.
    payload = b"\x47\x40\x00\x10" + bytes(range(256)) * 4

    push = unauthenticated_client.post(
        f"/api/cameras/{cam_id}/push-segment?filename=segment_00042.ts",
        content=payload,
        headers={"X-Node-API-Key": raw_key},
    )
    assert push.status_code == 200, push.text
    assert push.json()["success"] is True

    # Cache is populated server-side.
    assert cam_id in _segment_cache
    assert "segment_00042.ts" in _segment_cache[cam_id]

    fetch = admin_client.get(f"/api/cameras/{cam_id}/segment/segment_00042.ts")
    assert fetch.status_code == 200
    assert fetch.headers["content-type"] == "video/mp2t"
    assert fetch.content == payload


def test_segment_fetch_missing_returns_404(admin_client, db):
    """A filename that was never pushed must 404 — no accidental fallback
    to another camera's cache."""
    _raw_key, cam_id = _seed_node_with_camera(db)
    resp = admin_client.get(f"/api/cameras/{cam_id}/segment/segment_99999.ts")
    assert resp.status_code == 404


def test_segment_filename_rejects_path_traversal(
    admin_client, unauthenticated_client, db
):
    """The endpoint must reject anything that isn't ``segment_\\d+\\.ts``.
    A successful traversal here would let a node poison the cache for
    arbitrary keys or let a viewer request arbitrary files — both bad."""
    raw_key, cam_id = _seed_node_with_camera(db)

    bad_names = [
        "../secret.env",
        "segment_00001.ts/..",
        "seg.ts",
        "segment_a.ts",  # non-numeric
    ]
    for name in bad_names:
        push = unauthenticated_client.post(
            f"/api/cameras/{cam_id}/push-segment?filename={name}",
            content=b"\x00",
            headers={"X-Node-API-Key": raw_key},
        )
        assert push.status_code == 400, (name, push.text)

        fetch = admin_client.get(f"/api/cameras/{cam_id}/segment/{name}")
        # Either 400 (validation) or 404 (routing) is acceptable —
        # what matters is that we never 200 with real bytes.
        assert fetch.status_code in (400, 404), (name, fetch.status_code)


def test_push_segment_rejects_oversize(unauthenticated_client, db, monkeypatch):
    """SEGMENT_PUSH_MAX_BYTES is the safety valve keeping a malicious or
    buggy node from exhausting RAM — verify the cap actually fires."""
    from app.core.config import settings

    raw_key, cam_id = _seed_node_with_camera(db)
    # Pin to a tiny cap so the test doesn't have to ship a 2 MB blob.
    monkeypatch.setattr(settings, "SEGMENT_PUSH_MAX_BYTES", 128)

    resp = unauthenticated_client.post(
        f"/api/cameras/{cam_id}/push-segment?filename=segment_00001.ts",
        content=b"\x00" * 256,
        headers={"X-Node-API-Key": raw_key},
    )
    assert resp.status_code == 400
    assert "too large" in resp.json()["detail"].lower()


# ── Cache eviction ───────────────────────────────────────────────────


def test_segment_cache_evicts_oldest_when_over_limit(
    unauthenticated_client, db, monkeypatch
):
    """Push MAX+3 segments — only the newest MAX must remain.  This is
    the whole reason segments are keyed by monotonic filename prefix."""
    from app.api.hls import _segment_cache
    from app.core.config import settings

    raw_key, cam_id = _seed_node_with_camera(db)
    monkeypatch.setattr(settings, "SEGMENT_CACHE_MAX_PER_CAMERA", 5)

    for i in range(1, 9):  # 8 segments, cap is 5
        resp = unauthenticated_client.post(
            f"/api/cameras/{cam_id}/push-segment?filename=segment_{i:05d}.ts",
            content=bytes([i]),
            headers={"X-Node-API-Key": raw_key},
        )
        assert resp.status_code == 200

    cached = _segment_cache[cam_id]
    assert len(cached) == 5
    # Oldest three must be gone; newest five must remain.
    for i in range(1, 4):
        assert f"segment_{i:05d}.ts" not in cached
    for i in range(4, 9):
        assert f"segment_{i:05d}.ts" in cached


# ── Playlist rewriting ───────────────────────────────────────────────

_RAW_PLAYLIST = (
    "#EXTM3U\n"
    "#EXT-X-VERSION:3\n"
    "#EXT-X-TARGETDURATION:2\n"
    "#EXT-X-MEDIA-SEQUENCE:42\n"
    "#EXTINF:2.0,\n"
    "segment_00042.ts\n"
    "#EXTINF:2.0,\n"
    "segment_00043.ts\n"
    "#EXTINF:2.0,\n"
    "segment_00044.ts\n"
)


def test_playlist_segments_use_relative_proxy_paths(
    admin_client,
    unauthenticated_client,
    db,
):
    """After a CloudNode pushes a raw playlist, the cached rewrite served
    to the browser must route every segment through this backend via a
    relative path — never an absolute URL.  A stray absolute URL would
    bypass our auth layer and point the browser at someone else's host."""
    raw_key, cam_id = _seed_node_with_camera(db)

    push = unauthenticated_client.post(
        f"/api/cameras/{cam_id}/playlist",
        content=_RAW_PLAYLIST,
        headers={"X-Node-API-Key": raw_key},
    )
    assert push.status_code == 200

    fetch = admin_client.get(f"/api/cameras/{cam_id}/stream.m3u8")
    assert fetch.status_code == 200
    body = fetch.text

    # Relative proxy paths — browser resolves these against stream.m3u8.
    assert "segment/segment_00042.ts" in body
    assert "segment/segment_00043.ts" in body
    assert "segment/segment_00044.ts" in body

    # No absolute URLs and no presigned-style query params should ever
    # appear in a served playlist.
    lowered = body.lower()
    for marker in ("https://", "http://", "x-amz-", "?expires=", "&expires="):
        assert marker not in lowered, (marker, body)


def test_playlist_does_not_inject_codec_header(
    admin_client, unauthenticated_client, db
):
    """#EXT-X-CODECS is only valid in Master Playlists per HLS spec.
    Injecting it into Media Playlists causes hls.js to fail parsing."""
    raw_key, cam_id = _seed_node_with_camera(db)

    unauthenticated_client.post(
        f"/api/cameras/{cam_id}/playlist",
        content=_RAW_PLAYLIST,
        headers={"X-Node-API-Key": raw_key},
    )
    body = admin_client.get(f"/api/cameras/{cam_id}/stream.m3u8").text

    # No CODECS line in media playlist — codec info is in the bitstream
    assert "#EXT-X-CODECS:" not in body


def test_playlist_rewrite_handles_path_prefixed_segment_uris(
    admin_client,
    unauthenticated_client,
    db,
):
    """FFmpeg's HLS muxer sometimes writes the ``-hls_segment_filename``
    verbatim into the playlist URIs — so on a node where the segment
    filename is given with a relative path prefix (the production shape,
    ``./data/hls/<cam>/segment_%05d.ts``), the playlist contains lines
    like ``./data/hls/<cam>/segment_00042.ts`` instead of bare basenames.

    The rewriter must still normalize these to ``segment/<basename>``;
    otherwise the browser tries to fetch the stale relative path against
    its own origin and 404s — segments-pushing-but-nothing-playing,
    which is exactly the symptom we hit on a real Pi deploy.
    """
    raw_key, cam_id = _seed_node_with_camera(db)
    prefixed_playlist = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        "#EXT-X-TARGETDURATION:2\n"
        "#EXT-X-MEDIA-SEQUENCE:42\n"
        "#EXTINF:2.0,\n"
        "./data/hls/db2782d7_dev_video0/segment_00042.ts\n"
        "#EXTINF:2.0,\n"
        "./data/hls/db2782d7_dev_video0/segment_00043.ts\n"
    )

    push = unauthenticated_client.post(
        f"/api/cameras/{cam_id}/playlist",
        content=prefixed_playlist,
        headers={"X-Node-API-Key": raw_key},
    )
    assert push.status_code == 200

    body = admin_client.get(f"/api/cameras/{cam_id}/stream.m3u8").text
    # The path prefix must be stripped — we want the relative proxy URI
    # only, never the node-local filesystem path.
    assert "segment/segment_00042.ts" in body
    assert "segment/segment_00043.ts" in body
    assert "./data/hls/" not in body


def test_playlist_rewrite_handles_crlf_line_endings(
    admin_client,
    unauthenticated_client,
    db,
):
    """A CloudNode running on Windows can write the playlist with CRLF
    line endings.  The regex must treat ``\\r`` as trailing whitespace
    so the emitted URI is still the clean ``segment/<name>`` — a stray
    ``\\r`` in the middle of the URI would break the browser's fetch."""
    raw_key, cam_id = _seed_node_with_camera(db)
    crlf_playlist = (
        "#EXTM3U\r\n"
        "#EXT-X-VERSION:3\r\n"
        "#EXT-X-TARGETDURATION:2\r\n"
        "#EXT-X-MEDIA-SEQUENCE:10\r\n"
        "#EXTINF:2.0,\r\n"
        "segment_00010.ts\r\n"
        "#EXTINF:2.0,\r\n"
        "segment_00011.ts\r\n"
    )

    unauthenticated_client.post(
        f"/api/cameras/{cam_id}/playlist",
        content=crlf_playlist,
        headers={"X-Node-API-Key": raw_key},
    )

    body = admin_client.get(f"/api/cameras/{cam_id}/stream.m3u8").text
    # The URI line on its own — no stray \r glued onto the filename.
    assert "segment/segment_00010.ts\r" in body or "segment/segment_00010.ts\n" in body
    # The rewritten URI line should not contain ``\rsegment`` anywhere —
    # that'd mean a CR survived into the middle of the URI.
    assert "\rsegment" not in body.replace("\r\n", "\n")


def test_playlist_rewrite_is_idempotent_across_pushes(
    admin_client,
    unauthenticated_client,
    db,
):
    """Push the same raw playlist twice.  The served version should look
    the same — no doubled codec lines, no re-prefixed segment paths like
    ``segment/segment/segment_00042.ts``."""
    raw_key, cam_id = _seed_node_with_camera(db)
    headers = {"X-Node-API-Key": raw_key}

    unauthenticated_client.post(
        f"/api/cameras/{cam_id}/playlist",
        content=_RAW_PLAYLIST,
        headers=headers,
    )
    first = admin_client.get(f"/api/cameras/{cam_id}/stream.m3u8").text

    unauthenticated_client.post(
        f"/api/cameras/{cam_id}/playlist",
        content=_RAW_PLAYLIST,
        headers=headers,
    )
    second = admin_client.get(f"/api/cameras/{cam_id}/stream.m3u8").text

    assert first == second
    assert "segment/segment/" not in second
    # No CODECS line in media playlist
    assert "#EXT-X-CODECS:" not in second


def test_stream_without_push_returns_404(admin_client, db):
    """No cached playlist → 404.  The viewer learns the stream hasn't
    started yet rather than getting a bogus empty playlist."""
    _raw_key, cam_id = _seed_node_with_camera(db)
    resp = admin_client.get(f"/api/cameras/{cam_id}/stream.m3u8")
    assert resp.status_code == 404
    assert "not started" in resp.json()["detail"].lower()


# ── cleanup_camera_cache ─────────────────────────────────────────────


def test_cleanup_camera_cache_drops_segments_and_playlist(
    unauthenticated_client,
    db,
):
    """``cleanup_camera_cache`` is the function called from every delete
    path (camera delete, node delete, org delete, stale-camera sweep).
    It must scrub BOTH segment and playlist state for the camera — a
    stale playlist referencing now-deleted segments would break the next
    camera that happens to reuse the same id."""
    from app.api.hls import _segment_cache, _playlist_cache, cleanup_camera_cache

    raw_key, cam_id = _seed_node_with_camera(db)
    headers = {"X-Node-API-Key": raw_key}

    unauthenticated_client.post(
        f"/api/cameras/{cam_id}/push-segment?filename=segment_00001.ts",
        content=b"\x01\x02\x03",
        headers=headers,
    )
    unauthenticated_client.post(
        f"/api/cameras/{cam_id}/playlist",
        content=_RAW_PLAYLIST,
        headers=headers,
    )
    assert cam_id in _segment_cache
    assert cam_id in _playlist_cache

    cleanup_camera_cache(cam_id)

    assert cam_id not in _segment_cache
    assert cam_id not in _playlist_cache
    # Idempotent — calling again on an already-cleaned cam must not raise.
    cleanup_camera_cache(cam_id)
