"""Tests for motion detection event endpoints."""

import asyncio
from datetime import datetime, timedelta, timezone
from app.models.models import MotionEvent
from app.api.motion import motion_broadcaster


def test_list_motion_events_empty(viewer_client):
    """No motion events returns empty list."""
    resp = viewer_client.get("/api/motion/events")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0
    assert data["events"] == []


def test_list_motion_events_with_data(viewer_client, db):
    """Motion events are returned in reverse chronological order."""
    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    for i in range(3):
        db.add(MotionEvent(
            org_id="org_test123",
            camera_id="cam_front",
            node_id="node_1",
            score=50 + i * 10,
            segment_seq=100 + i,
            timestamp=now - timedelta(minutes=10 - i),
        ))
    db.commit()

    resp = viewer_client.get("/api/motion/events")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["events"]) == 3
    # Most recent first
    assert data["events"][0]["score"] == 70
    assert data["events"][2]["score"] == 50


def test_list_motion_events_camera_filter(viewer_client, db):
    """Filtering by camera_id returns only matching events."""
    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    db.add(MotionEvent(org_id="org_test123", camera_id="cam_front", node_id="n1", score=80, timestamp=now))
    db.add(MotionEvent(org_id="org_test123", camera_id="cam_back", node_id="n1", score=60, timestamp=now))
    db.commit()

    resp = viewer_client.get("/api/motion/events?camera_id=cam_front")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["events"][0]["camera_id"] == "cam_front"


def test_motion_events_org_isolation(viewer_client, db):
    """Events from other orgs are not visible."""
    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    db.add(MotionEvent(org_id="org_test123", camera_id="cam_1", node_id="n1", score=90, timestamp=now))
    db.add(MotionEvent(org_id="org_other", camera_id="cam_2", node_id="n2", score=85, timestamp=now))
    db.commit()

    resp = viewer_client.get("/api/motion/events")
    data = resp.json()
    assert data["total"] == 1
    assert data["events"][0]["camera_id"] == "cam_1"


def test_motion_stats(viewer_client, db):
    """Stats endpoint returns per-camera aggregates."""
    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    for score in [40, 60, 80]:
        db.add(MotionEvent(
            org_id="org_test123", camera_id="cam_front", node_id="n1",
            score=score, timestamp=now - timedelta(minutes=score),
        ))
    db.add(MotionEvent(
        org_id="org_test123", camera_id="cam_back", node_id="n1",
        score=95, timestamp=now,
    ))
    db.commit()

    resp = viewer_client.get("/api/motion/events/stats")
    assert resp.status_code == 200
    data = resp.json()
    cameras = {c["camera_id"]: c for c in data["cameras"]}
    assert len(cameras) == 2
    assert cameras["cam_front"]["event_count"] == 3
    assert cameras["cam_front"]["peak_score"] == 80
    assert cameras["cam_back"]["event_count"] == 1
    assert cameras["cam_back"]["peak_score"] == 95


def test_motion_broadcaster_delivers():
    """MotionBroadcaster pushes events to subscribers for the matching org."""
    q = motion_broadcaster.subscribe("org_A")
    q_other = motion_broadcaster.subscribe("org_B")

    motion_broadcaster.notify("org_A", {"camera_id": "cam1", "score": 75})

    assert not q.empty()
    event = q.get_nowait()
    assert event["camera_id"] == "cam1"
    assert event["score"] == 75

    # Other org's queue should be empty
    assert q_other.empty()

    motion_broadcaster.unsubscribe("org_A", q)
    motion_broadcaster.unsubscribe("org_B", q_other)


def test_motion_broadcaster_unsubscribe():
    """Unsubscribed queues stop receiving events."""
    q = motion_broadcaster.subscribe("org_unsub")
    motion_broadcaster.unsubscribe("org_unsub", q)

    motion_broadcaster.notify("org_unsub", {"camera_id": "cam2", "score": 50})
    assert q.empty()
