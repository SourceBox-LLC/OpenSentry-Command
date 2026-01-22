"""
MQTT client for OpenSentry Command Center.
Handles communication with camera nodes via MQTT broker.
"""

import ssl
import time
import json
import hashlib
import paho.mqtt.client as mqtt

from ..models.camera import CAMERAS, cameras_lock
from ..config import Config

# Global reference to Flask app for alert logging
_flask_app = None


def set_flask_app(app):
    """Set the Flask app reference for use in MQTT callbacks"""
    global _flask_app
    _flask_app = app


def log_alert_to_db(
    camera_id,
    detection_type,
    confidence=0,
    region_x=None,
    region_y=None,
    region_width=None,
    region_height=None,
):
    """Log an alert to the database - called from MQTT callbacks"""
    global _flask_app
    if _flask_app is None:
        print(f"[Alerts] Cannot log {detection_type} alert - app not ready")
        return

    try:
        with _flask_app.app_context():
            from ..models.database import Alert, db

            alert = Alert(
                camera_id=camera_id,
                detection_type=detection_type,
                confidence=confidence,
                region_x=region_x,
                region_y=region_y,
                region_width=region_width,
                region_height=region_height,
            )
            db.session.add(alert)
            db.session.commit()
            print(f"[Alerts] Logged {detection_type} alert from {camera_id}")
    except Exception as e:
        print(f"[Alerts] Failed to log {detection_type} alert: {e}")


def derive_credential(secret: str, service: str) -> str:
    """Derive a credential from a secret and service name using SHA256"""
    input_str = f"{secret}:{service}"
    hash_bytes = hashlib.sha256(input_str.encode()).hexdigest()
    return hash_bytes[:32]


def _get_mqtt_credentials():
    """Get MQTT credentials (derived or legacy)"""
    if Config.OPENSENTRY_SECRET:
        print("[MQTT] Using derived credentials from OPENSENTRY_SECRET")
        return "opensentry", derive_credential(Config.OPENSENTRY_SECRET, "mqtt")
    else:
        return Config.MQTT_USERNAME, Config.MQTT_PASSWORD


MQTT_USERNAME, MQTT_PASSWORD = _get_mqtt_credentials()

# MQTT Client instance
_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=Config.MQTT_CLIENT_ID)
_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

# Configure TLS if enabled
if Config.MQTT_USE_TLS:
    # Create SSL context that accepts self-signed certificates
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE  # Accept self-signed certs
    _client.tls_set_context(ssl_context)
    print("[MQTT] 🔒 TLS encryption enabled")


def _on_connect(client, userdata, flags, reason_code, properties):
    """Called when connected to MQTT broker"""
    print(f"[MQTT] Connected with result code {reason_code}")
    client.subscribe("opensentry/+/status")
    print("[MQTT] Subscribed to opensentry/+/status")
    client.subscribe("opensentry/+/motion")
    print("[MQTT] Subscribed to opensentry/+/motion")
    client.subscribe("opensentry/+/face")
    print("[MQTT] Subscribed to opensentry/+/face")
    client.subscribe("opensentry/+/objects")
    print("[MQTT] Subscribed to opensentry/+/objects")


def _on_message(client, userdata, msg):
    """Called when a message is received from MQTT"""
    topic = msg.topic
    payload = msg.payload.decode("utf-8")

    parts = topic.split("/")
    if len(parts) == 3 and parts[0] == "opensentry":
        camera_id = parts[1]
        message_type = parts[2]

        if message_type == "status":
            if camera_id in CAMERAS:
                # Try to parse as JSON first (new format)
                try:
                    status_data = json.loads(payload)

                    # Extract status and additional info from JSON
                    CAMERAS[camera_id]["status"] = status_data.get("status", payload)

                    # Update node type and capabilities if provided
                    if "node_type" in status_data:
                        CAMERAS[camera_id]["node_type"] = status_data["node_type"]
                    if "capabilities" in status_data:
                        CAMERAS[camera_id]["capabilities"] = status_data["capabilities"]

                    CAMERAS[camera_id]["last_seen"] = time.time()
                    print(
                        f"[MQTT] {camera_id} status: {status_data.get('status')} (type: {status_data.get('node_type', 'unknown')})"
                    )

                except (json.JSONDecodeError, TypeError):
                    # Fallback to plain text status (backward compatibility)
                    CAMERAS[camera_id]["status"] = payload
                    CAMERAS[camera_id]["last_seen"] = time.time()
                    print(f"[MQTT] {camera_id} status: {payload}")

        elif message_type == "motion":
            if camera_id in CAMERAS:
                # Parse motion event JSON
                try:
                    motion_data = json.loads(payload)

                    # Store motion event in camera data
                    if "motion_events" not in CAMERAS[camera_id]:
                        CAMERAS[camera_id]["motion_events"] = []

                    # Keep last 100 motion events
                    CAMERAS[camera_id]["motion_events"].append(motion_data)
                    if len(CAMERAS[camera_id]["motion_events"]) > 100:
                        CAMERAS[camera_id]["motion_events"].pop(0)

                    # Update motion status
                    if motion_data.get("event") == "motion_start":
                        CAMERAS[camera_id]["motion_active"] = True
                        # Log the motion alert with region data
                        log_alert_to_db(
                            camera_id,
                            "motion",
                            motion_data.get("confidence", 0),
                            region_x=motion_data.get("area_x"),
                            region_y=motion_data.get("area_y"),
                            region_width=motion_data.get("area_width"),
                            region_height=motion_data.get("area_height"),
                        )
                        print(
                            f"[MQTT] {camera_id} motion started at area ({motion_data.get('area_x')}, {motion_data.get('area_y')})"
                        )
                    elif motion_data.get("event") == "motion_end":
                        CAMERAS[camera_id]["motion_active"] = False
                        print(
                            f"[MQTT] {camera_id} motion ended, duration: {motion_data.get('duration')}s"
                        )

                except Exception as e:
                    print(f"[MQTT] Error parsing motion event: {e}")

        elif message_type == "face":
            if camera_id in CAMERAS:
                try:
                    face_data = json.loads(payload)

                    if "face_events" not in CAMERAS[camera_id]:
                        CAMERAS[camera_id]["face_events"] = []

                    CAMERAS[camera_id]["face_events"].append(face_data)
                    if len(CAMERAS[camera_id]["face_events"]) > 100:
                        CAMERAS[camera_id]["face_events"].pop(0)

                    if face_data.get("event") == "face_detected":
                        CAMERAS[camera_id]["face_active"] = True
                        # Get face region (typically first face bbox)
                        face_regions = face_data.get("faces", [])
                        first_face = face_regions[0] if face_regions else {}
                        # Log the face alert
                        log_alert_to_db(
                            camera_id,
                            "face",
                            face_data.get("max_confidence", 0),
                            region_x=first_face.get("x"),
                            region_y=first_face.get("y"),
                            region_width=first_face.get("width"),
                            region_height=first_face.get("height"),
                        )
                        print(
                            f"[MQTT] {camera_id} face detected: {face_data.get('count')} face(s), confidence: {face_data.get('max_confidence', 0):.2f}"
                        )
                    elif face_data.get("event") == "face_end":
                        CAMERAS[camera_id]["face_active"] = False
                        print(
                            f"[MQTT] {camera_id} face ended, duration: {face_data.get('duration')}s"
                        )

                except Exception as e:
                    print(f"[MQTT] Error parsing face event: {e}")

        elif message_type == "objects":
            if camera_id in CAMERAS:
                try:
                    objects_data = json.loads(payload)

                    if "object_events" not in CAMERAS[camera_id]:
                        CAMERAS[camera_id]["object_events"] = []

                    CAMERAS[camera_id]["object_events"].append(objects_data)
                    if len(CAMERAS[camera_id]["object_events"]) > 100:
                        CAMERAS[camera_id]["object_events"].pop(0)

                    if objects_data.get("event") == "objects_detected":
                        CAMERAS[camera_id]["objects_active"] = True
                        # Log the object alert
                        objects_list = objects_data.get("objects", [])
                        max_confidence = max(
                            (obj.get("confidence", 0) for obj in objects_list),
                            default=0,
                        )
                        # Get region from first object
                        first_obj = objects_list[0] if objects_list else {}
                        log_alert_to_db(
                            camera_id,
                            "object",
                            max_confidence,
                            region_x=first_obj.get("x"),
                            region_y=first_obj.get("y"),
                            region_width=first_obj.get("width"),
                            region_height=first_obj.get("height"),
                        )

                        object_names = [
                            obj.get("class", "unknown") for obj in objects_list
                        ]
                        print(
                            f"[MQTT] {camera_id} objects detected: {', '.join(object_names)}"
                        )
                    elif objects_data.get("event") == "objects_cleared":
                        CAMERAS[camera_id]["objects_active"] = False
                        print(f"[MQTT] {camera_id} objects cleared")

                except Exception as e:
                    print(f"[MQTT] Error parsing objects event: {e}")


def _on_disconnect(client, userdata, flags, reason_code, properties):
    """Called when disconnected from MQTT broker"""
    print(f"[MQTT] Disconnected with result code {reason_code}")


# Register callbacks
_client.on_connect = _on_connect
_client.on_message = _on_message
_client.on_disconnect = _on_disconnect


def start():
    """Start MQTT client in background thread with auto-reconnect"""
    _client.reconnect_delay_set(min_delay=1, max_delay=30)
    try:
        _client.connect(Config.MQTT_BROKER, Config.MQTT_PORT, 60)
        _client.loop_start()
        print("[MQTT] Client started")
    except Exception as e:
        print(f"[MQTT] Initial connection failed: {e}")
        print("[MQTT] Will retry in background...")
        _client.loop_start()


def stop():
    """Stop MQTT client"""
    _client.loop_stop()
    _client.disconnect()
    print("[MQTT] Client stopped")


def send_command(camera_id: str, command: str) -> bool:
    """Send a command to a camera node via MQTT"""
    topic = f"opensentry/{camera_id}/command"
    result = _client.publish(topic, command)

    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print(f"[MQTT] Sent command '{command}' to {camera_id}")
        return True
    else:
        print(f"[MQTT] Failed to send command '{command}' to {camera_id}")
        return False
