"""
MQTT client for OpenSentry Command Center.
Handles communication with camera nodes via MQTT broker.
"""
import ssl
import time
import hashlib
import paho.mqtt.client as mqtt

from ..models.camera import CAMERAS, cameras_lock
from ..config import Config


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


def _on_message(client, userdata, msg):
    """Called when a message is received from MQTT"""
    topic = msg.topic
    payload = msg.payload.decode('utf-8')
    
    parts = topic.split('/')
    if len(parts) == 3 and parts[0] == 'opensentry' and parts[2] == 'status':
        camera_id = parts[1]
        
        if camera_id in CAMERAS:
            CAMERAS[camera_id]['status'] = payload
            CAMERAS[camera_id]['last_seen'] = time.time()
            print(f"[MQTT] {camera_id} status: {payload}")


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
