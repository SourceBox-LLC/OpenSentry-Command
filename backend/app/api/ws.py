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
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import CameraNode, Camera

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
        # Pending command futures: {correlation_id: asyncio.Future}
        self._pending_commands: dict[str, asyncio.Future] = {}

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

        correlation_id = str(uuid.uuid4())[:8]
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_commands[correlation_id] = future

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
        finally:
            self._pending_commands.pop(correlation_id, None)

    def resolve_command(self, correlation_id: str, result: dict):
        """Called when a command_result message arrives from a node."""
        future = self._pending_commands.get(correlation_id)
        if future and not future.done():
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
                    "payload": {"timestamp": datetime.utcnow().isoformat()},
                })

            elif msg_type == "command_result":
                correlation_id = data.get("id")
                if correlation_id:
                    manager.resolve_command(correlation_id, data.get("payload", {}))

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
    """Process a heartbeat message — same logic as the HTTP endpoint."""
    db: Session = SessionLocal()
    try:
        node = db.query(CameraNode).filter_by(node_id=node_id).first()
        if not node:
            return

        node.status = "online"
        node.last_seen = datetime.utcnow()

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
                now = datetime.utcnow()
                for cam_data in cameras:
                    cam = cam_map.get(cam_data.get("camera_id"))
                    if cam:
                        cam.status = cam_data.get("status", "online")
                        cam.last_seen = now

        db.commit()
    except Exception as e:
        logger.error("Heartbeat DB error for node %s: %s", node_id, e)
        db.rollback()
    finally:
        db.close()
