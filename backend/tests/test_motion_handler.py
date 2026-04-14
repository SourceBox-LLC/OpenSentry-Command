"""Tests for the _handle_motion_event defensive branches in ws.py."""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch

from app.api.ws import _handle_motion_event
from app.models.models import Camera, CameraNode, MotionEvent


def _seed_node_and_cameras(db, node_id="node1", org_id="org_test123", cameras=("cam1", "cam2")):
    """Insert a CameraNode plus the given Cameras so the ownership check
    in ``_handle_motion_event`` lets the event through."""
    node = CameraNode(
        node_id=node_id,
        org_id=org_id,
        api_key_hash="unused-in-tests",
        name=f"Test {node_id}",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    for cid in cameras:
        db.add(Camera(
            camera_id=cid,
            org_id=org_id,
            node_id=node.id,
            name=cid,
        ))
    db.commit()


@pytest.mark.asyncio
async def test_missing_camera_id(db):
    """Events without camera_id are silently dropped."""
    _seed_node_and_cameras(db)
    await _handle_motion_event("node1", "org_test123", {"score": 50})
    assert db.query(MotionEvent).count() == 0


@pytest.mark.asyncio
async def test_missing_score(db):
    """Events without score are silently dropped."""
    _seed_node_and_cameras(db)
    await _handle_motion_event("node1", "org_test123", {"camera_id": "cam1"})
    assert db.query(MotionEvent).count() == 0


@pytest.mark.asyncio
async def test_non_numeric_score(db):
    """Non-numeric score values are rejected."""
    _seed_node_and_cameras(db)
    await _handle_motion_event("node1", "org_test123", {
        "camera_id": "cam1", "score": "not_a_number",
    })
    assert db.query(MotionEvent).count() == 0


@pytest.mark.asyncio
async def test_score_clamped_to_range(db):
    """Scores outside 0-100 are clamped, not rejected."""
    _seed_node_and_cameras(db)
    await _handle_motion_event("node1", "org_test123", {
        "camera_id": "cam1", "score": 250,
    })
    event = db.query(MotionEvent).first()
    assert event is not None
    assert event.score == 100

    await _handle_motion_event("node1", "org_test123", {
        "camera_id": "cam2", "score": -10,
    })
    event2 = db.query(MotionEvent).filter_by(camera_id="cam2").first()
    assert event2.score == 0


@pytest.mark.asyncio
async def test_unparseable_timestamp_uses_server_time(db):
    """Invalid timestamps fall back to server time rather than failing."""
    _seed_node_and_cameras(db)
    before = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    await _handle_motion_event("node1", "org_test123", {
        "camera_id": "cam1", "score": 75, "timestamp": "not-a-date",
    })
    after = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    event = db.query(MotionEvent).first()
    assert event is not None
    assert before <= event.timestamp <= after


@pytest.mark.asyncio
async def test_valid_iso_timestamp_preserved(db):
    """Valid ISO 8601 timestamps are used as-is."""
    _seed_node_and_cameras(db)
    await _handle_motion_event("node1", "org_test123", {
        "camera_id": "cam1", "score": 60,
        "timestamp": "2026-01-15T10:30:00",
    })
    event = db.query(MotionEvent).first()
    assert event.timestamp.year == 2026
    assert event.timestamp.month == 1
    assert event.timestamp.hour == 10


@pytest.mark.asyncio
async def test_non_numeric_segment_seq(db):
    """Non-numeric segment_seq is stored as None."""
    _seed_node_and_cameras(db)
    await _handle_motion_event("node1", "org_test123", {
        "camera_id": "cam1", "score": 80, "segment_seq": "abc",
    })
    event = db.query(MotionEvent).first()
    assert event is not None
    assert event.segment_seq is None


@pytest.mark.asyncio
async def test_valid_event_persisted_and_broadcast(db):
    """A fully valid event is persisted and broadcast to SSE subscribers."""
    from app.api.motion import motion_broadcaster

    _seed_node_and_cameras(db)
    q = motion_broadcaster.subscribe("org_test123")
    await _handle_motion_event("node1", "org_test123", {
        "camera_id": "cam1", "score": 72,
        "timestamp": "2026-04-12T14:00:00", "segment_seq": 42,
    })

    # DB
    event = db.query(MotionEvent).first()
    assert event is not None
    assert event.camera_id == "cam1"
    assert event.score == 72
    assert event.segment_seq == 42

    # SSE broadcast
    assert not q.empty()
    broadcast = q.get_nowait()
    assert broadcast["type"] == "motion"
    assert broadcast["camera_id"] == "cam1"
    assert broadcast["score"] == 72

    motion_broadcaster.unsubscribe("org_test123", q)


# ── M4: camera ownership rejection ──────────────────────────────────

@pytest.mark.asyncio
async def test_rejects_event_for_unknown_node(db):
    """A node_id/org_id combo that doesn't exist is rejected — motion
    events must never land in an org the authenticated node doesn't
    belong to."""
    # No seed — DB has no nodes.
    await _handle_motion_event("node-ghost", "org_test123", {
        "camera_id": "cam1", "score": 55,
    })
    assert db.query(MotionEvent).count() == 0


@pytest.mark.asyncio
async def test_rejects_event_for_camera_not_on_node(db):
    """A camera_id that exists but belongs to a different node is
    rejected — a compromised node can't spam events referencing
    another node's cameras."""
    # Seed node1 + cam1, plus a separate node2 that owns cam2.
    _seed_node_and_cameras(db, node_id="node1", cameras=("cam1",))
    node2 = CameraNode(
        node_id="node2",
        org_id="org_test123",
        api_key_hash="unused-in-tests",
        name="Test node2",
    )
    db.add(node2)
    db.commit()
    db.refresh(node2)
    db.add(Camera(
        camera_id="cam2", org_id="org_test123", node_id=node2.id, name="cam2",
    ))
    db.commit()

    # node1 tries to push a motion event for cam2 (owned by node2).
    await _handle_motion_event("node1", "org_test123", {
        "camera_id": "cam2", "score": 90,
    })
    assert db.query(MotionEvent).count() == 0


@pytest.mark.asyncio
async def test_rejects_event_for_other_orgs_camera(db):
    """Even when the camera_id exists globally, a node in org A cannot
    push events against a camera in org B.  ``org_id`` in the handler
    comes from the authenticated WS session so this test locks in
    defense-in-depth against schema drift."""
    # Seed a node+camera in org_A…
    _seed_node_and_cameras(db, node_id="node-a", org_id="org_A", cameras=("cam-A",))
    # …and a node+camera in org_B with a DIFFERENT camera_id (camera_id
    # is globally unique so we can't reuse "cam-A"; the point here is
    # that node-a authenticated into org_A cannot touch cam-B).
    _seed_node_and_cameras(db, node_id="node-b", org_id="org_B", cameras=("cam-B",))

    # node-a (authenticated into org_A) tries to push an event for cam-B.
    await _handle_motion_event("node-a", "org_A", {
        "camera_id": "cam-B", "score": 60,
    })
    assert db.query(MotionEvent).count() == 0
