"""
WebSocket command channel for CloudNode ↔ Backend communication.

Nodes connect outbound to ws://<backend>/ws/node?api_key=<key>&node_id=<id>
and maintain a persistent bidirectional JSON message channel.

Message format (both directions):
    {"type": "<message_type>", "id": "<optional_correlation_id>", "payload": {...}}

Node → Backend types:
    heartbeat       — periodic camera status update
    command_result  — response to a backend-issued command

Backend → Node types:
    ack             — heartbeat acknowledged
    command         — request the node to do something (snapshot, recording, etc.)
    error           — something went wrong
"""

import asyncio
import hashlib
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import CameraNode, Camera, MotionEvent

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Connection Manager ────────────────────────────────────────────────
# Tracks all active WebSocket connections keyed by node_id.
# Provides methods to send commands to specific nodes and wait for
# responses via correlation IDs.

class ConnectionManager:
    def __init__(self):
        # {node_id: WebSocket}
        self._connections: dict[str, WebSocket] = {}
        # Pending command futures: {correlation_id: (node_id, asyncio.Future)}
        self._pending_commands: dict[str, tuple[str, asyncio.Future]] = {}

    @property
    def connected_nodes(self) -> list[str]:
        return list(self._connections.keys())

    def is_connected(self, node_id: str) -> bool:
        return node_id in self._connections

    async def connect(self, node_id: str, ws: WebSocket):
        # Close any existing connection for this node (stale reconnect)
        old = self._connections.get(node_id)
        if old:
            try:
                await old.close(code=1000, reason="Replaced by new connection")
            except Exception:
                pass
        self._connections[node_id] = ws
        # Use print() so it always appears in fly logs (logger.info is filtered by default)
        print(f"[WS] Node {node_id} connected via WebSocket")

    def disconnect(self, node_id: str):
        self._connections.pop(node_id, None)
        # Cancel pending command futures so callers don't wait until
        # timeout for a node that's already gone.
        stale = [cid for cid, (nid, _) in self._pending_commands.items() if nid == node_id]
        for cid in stale:
            _, future = self._pending_commands.pop(cid)
            if not future.done():
                future.cancel()
        print(f"[WS] Node {node_id} disconnected from WebSocket")

    async def send_command(
        self,
        node_id: str,
        command: str,
        payload: dict | None = None,
        timeout: float = 30.0,
    ) -> dict:
        """
        Send a command to a node and wait for the response.
        Returns the command_result payload or raises TimeoutError/ValueError.
        """
        ws = self._connections.get(node_id)
        if not ws:
            raise ValueError(f"Node {node_id} is not connected")

        correlation_id = str(uuid.uuid4())
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending_commands[correlation_id] = (node_id, future)

        try:
            await ws.send_json({
                "type": "command",
                "id": correlation_id,
                "command": command,
                "payload": payload or {},
            })
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Command {command} to node {node_id} timed out")
        except asyncio.CancelledError:
            raise ValueError(f"Node {node_id} disconnected while awaiting {command}")
        finally:
            self._pending_commands.pop(correlation_id, None)

    def resolve_command(self, correlation_id: str, result: dict):
        """Called when a command_result message arrives from a node."""
        entry = self._pending_commands.get(correlation_id)
        if entry:
            _, future = entry
            if not future.done():
                future.set_result(result)


# Singleton — imported by other modules to send commands to nodes.
manager = ConnectionManager()


# ── WebSocket Endpoint ────────────────────────────────────────────────

@router.websocket("/ws/node")
async def node_websocket(
    ws: WebSocket,
    api_key: str = Query(...),
    node_id: str = Query(...),
):
    """
    Persistent WebSocket channel for a CloudNode.
    Authentication happens during handshake via query params.
    """
    # --- Authenticate ---
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    db: Session = SessionLocal()
    try:
        node = db.query(CameraNode).filter_by(node_id=node_id).first()
        if not node or node.api_key_hash != api_key_hash:
            print(f"[WS] Auth failed for node_id={node_id} (found={node is not None})")
            await ws.close(code=4001, reason="Invalid node_id or API key")
            return
        org_id = node.org_id
        node_db_id = node.id
    finally:
        db.close()

    await ws.accept()
    await manager.connect(node_id, ws)

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "heartbeat":
                await _handle_heartbeat(node_id, node_db_id, org_id, data.get("payload", {}))
                await ws.send_json({
                    "type": "ack",
                    "id": data.get("id"),
                    "payload": {"timestamp": datetime.now(tz=timezone.utc).replace(tzinfo=None).isoformat()},
                })

            elif msg_type == "command_result":
                correlation_id = data.get("id")
                if correlation_id:
                    manager.resolve_command(correlation_id, data.get("payload", {}))

            elif msg_type == "event":
                command = data.get("command")
                payload = data.get("payload", {})
                if command == "motion_detected":
                    await _handle_motion_event(node_id, org_id, payload)
                else:
                    logger.debug("Unhandled event command from node %s: %s", node_id, command)

            else:
                logger.warning("Unknown WS message type from node %s: %s", node_id, msg_type)
                await ws.send_json({
                    "type": "error",
                    "id": data.get("id"),
                    "payload": {"detail": f"Unknown message type: {msg_type}"},
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket error for node %s: %s", node_id, e)
    finally:
        manager.disconnect(node_id)


# ── Heartbeat Handler ─────────────────────────────────────────────────

async def _handle_heartbeat(node_id: str, node_db_id: int, org_id: str, payload: dict):
    """Process a heartbeat message — same logic as the HTTP endpoint.

    Also detects node/camera online↔offline transitions by comparing the
    previous ``status`` column against the incoming value; any change is
    emitted as a notification AFTER the DB commit so the inbox never
    shows a transition that later got rolled back.
    """
    db: Session = SessionLocal()

    # Accumulate transitions during the update pass so we can emit them
    # post-commit.  Tuple shape: (kind, entity_id, display_name, new_status, node_id|None)
    transitions: list[tuple[str, str, str, str, Optional[str]]] = []

    try:
        node = db.query(CameraNode).filter_by(node_id=node_id).first()
        if not node:
            return

        prev_node_status = node.status
        node.status = "online"
        node.last_seen = datetime.now(tz=timezone.utc).replace(tzinfo=None)

        if prev_node_status != "online":
            transitions.append(("node", node.node_id, node.name or node.node_id, "online", None))

        local_ip = payload.get("local_ip")
        if local_ip:
            node.local_ip = local_ip

        cameras = payload.get("cameras", [])
        if cameras:
            camera_ids = [c["camera_id"] for c in cameras if "camera_id" in c]
            if camera_ids:
                cams = db.query(Camera).filter(
                    Camera.camera_id.in_(camera_ids),
                    Camera.node_id == node_db_id,
                ).all()
                cam_map = {c.camera_id: c for c in cams}
                now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
                for cam_data in cameras:
                    cam = cam_map.get(cam_data.get("camera_id"))
                    if cam:
                        prev_cam_status = cam.status
                        new_cam_status = cam_data.get("status", "online")
                        cam.status = new_cam_status
                        cam.last_seen = now
                        if (
                            prev_cam_status != new_cam_status
                            and new_cam_status in ("online", "offline")
                        ):
                            display = cam.name or cam.camera_id
                            transitions.append(
                                ("camera", cam.camera_id, display, new_cam_status, node_id)
                            )

        db.commit()
    except Exception as e:
        logger.error("Heartbeat DB error for node %s: %s", node_id, e)
        db.rollback()
        return
    finally:
        # We leave db open briefly below to reuse for notification writes,
        # then close in the emit block's finally.
        pass

    # Emit transitions post-commit — any failure here must not fail the
    # heartbeat loop.  Reuse the same session for efficiency.
    if transitions:
        try:
            from app.api.notifications import (
                emit_camera_transition,
                emit_node_transition,
            )
            for kind, eid, name, new_status, cam_node_id in transitions:
                if kind == "node":
                    emit_node_transition(
                        db,
                        node_id=eid,
                        org_id=org_id,
                        display_name=name,
                        new_status=new_status,
                    )
                elif kind == "camera":
                    emit_camera_transition(
                        db,
                        camera_id=eid,
                        org_id=org_id,
                        display_name=name,
                        new_status=new_status,
                        node_id=cam_node_id,
                    )
        except Exception:
            logger.exception("[Heartbeat] Failed to emit transition notifications")

    db.close()


# ── Motion Event Handler ─────────────────────────────────────────────

async def _handle_motion_event(node_id: str, org_id: str, payload: dict):
    """Persist a motion detection event reported by a CloudNode."""
    camera_id = payload.get("camera_id")
    score = payload.get("score")
    segment_seq = payload.get("segment_seq")
    event_ts = payload.get("timestamp")  # ISO 8601 from node

    if not camera_id or score is None:
        logger.warning("Motion event from node %s missing camera_id or score", node_id)
        return

    # Normalise and clamp score to 0-100
    try:
        score_int = max(0, min(100, int(score)))
    except (ValueError, TypeError):
        logger.warning("Motion event from node %s has non-numeric score: %r", node_id, score)
        return

    ts = None
    if event_ts:
        try:
            ts = datetime.fromisoformat(event_ts).replace(tzinfo=None)
        except (ValueError, TypeError):
            logger.debug("Unparseable timestamp from node %s, using server time", node_id)
    if ts is None:
        ts = datetime.now(tz=timezone.utc).replace(tzinfo=None)

    try:
        seq = int(segment_seq) if segment_seq is not None else None
    except (ValueError, TypeError):
        seq = None

    db: Session = SessionLocal()
    try:
        # Verify the camera_id in the payload actually belongs to the
        # authenticated node in the authenticated org.  Without this
        # check a compromised node could spam its own org's inbox with
        # motion events referencing camera IDs it doesn't own (or that
        # don't exist).  Cross-tenant is still blocked because org_id
        # comes from the auth'd session, not the payload.
        from app.models.models import Camera as _Camera
        from app.models.models import CameraNode as _CameraNode

        owning_node = (
            db.query(_CameraNode)
            .filter_by(node_id=node_id, org_id=org_id)
            .first()
        )
        if not owning_node:
            logger.warning(
                "Motion event rejected: node %s not found in org %s", node_id, org_id,
            )
            return
        cam_row = (
            db.query(_Camera)
            .filter_by(camera_id=camera_id, node_id=owning_node.id, org_id=org_id)
            .first()
        )
        if not cam_row:
            logger.warning(
                "Motion event rejected: camera %s not owned by node %s (org %s)",
                camera_id, node_id, org_id,
            )
            return

        event = MotionEvent(
            org_id=org_id,
            camera_id=camera_id,
            node_id=node_id,
            score=score_int,
            segment_seq=seq,
            timestamp=ts,
        )
        db.add(event)
        db.commit()
        logger.info(
            "Motion event: camera=%s score=%d%% node=%s",
            camera_id, score_int, node_id,
        )

        # Broadcast to the motion SSE stream so live dashboards show
        # toasts immediately; the inbox notification below handles the
        # durable history.
        from app.api.motion import motion_broadcaster
        motion_broadcaster.notify(org_id, {
            "type": "motion",
            "camera_id": camera_id,
            "node_id": node_id,
            "score": score_int,
            "timestamp": ts.isoformat(),
        })

        # Also emit an inbox notification so the user can see motion
        # history in the bell panel.  Resolve the camera name for a
        # friendlier title — fall back to the camera_id if not found.
        try:
            from app.models.models import Camera
            from app.api.notifications import create_notification

            cam = (
                db.query(Camera)
                .filter_by(camera_id=camera_id, org_id=org_id)
                .first()
            )
            display_name = cam.name if cam and cam.name else camera_id

            create_notification(
                org_id=org_id,
                kind="motion",
                title=f"Motion on {display_name}",
                body=f"Scene change detected at {score_int}% intensity.",
                severity="info",
                audience="all",
                link=f"/dashboard?camera={camera_id}",
                camera_id=camera_id,
                node_id=node_id,
                meta={
                    "score": score_int,
                    "segment_seq": seq,
                    "event_timestamp": ts.isoformat(),
                },
                db=db,
            )
        except Exception:
            # Notification creation must never fail the motion event path.
            logger.exception("[Motion] Failed to create inbox notification")
    except Exception as e:
        logger.error("Failed to save motion event: %s", e)
        db.rollback()
    finally:
        db.close()
