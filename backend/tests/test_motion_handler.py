"""Tests for the _handle_motion_event defensive branches in ws.py."""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch

from app.api.ws import _handle_motion_event
from app.models.models import MotionEvent


@pytest.mark.asyncio
async def test_missing_camera_id(db):
    """Events without camera_id are silently dropped."""
    await _handle_motion_event("node1", "org_test123", {"score": 50})
    assert db.query(MotionEvent).count() == 0


@pytest.mark.asyncio
async def test_missing_score(db):
    """Events without score are silently dropped."""
    await _handle_motion_event("node1", "org_test123", {"camera_id": "cam1"})
    assert db.query(MotionEvent).count() == 0


@pytest.mark.asyncio
async def test_non_numeric_score(db):
    """Non-numeric score values are rejected."""
    await _handle_motion_event("node1", "org_test123", {
        "camera_id": "cam1", "score": "not_a_number",
    })
    assert db.query(MotionEvent).count() == 0


@pytest.mark.asyncio
async def test_score_clamped_to_range(db):
    """Scores outside 0-100 are clamped, not rejected."""
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
