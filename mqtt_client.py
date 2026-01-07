"""
MQTT client for OpenSentry Command Center.
Handles communication with camera nodes via MQTT broker.
"""
import time
import paho.mqtt.client as mqtt

from camera_registry import CAMERAS, cameras_lock

# MQTT Configuration
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_CLIENT_ID = "opensentry_command_center"

# MQTT Client instance
_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)


def _on_connect(client, userdata, flags, reason_code, properties):
    """Called when connected to MQTT broker"""
    print(f"[MQTT] Connected with result code {reason_code}")
    # Subscribe to all camera status topics
    client.subscribe("opensentry/+/status")
    print("[MQTT] Subscribed to opensentry/+/status")




def _on_message(client, userdata, msg):
    """Called when a message is received from MQTT"""
    topic = msg.topic
    payload = msg.payload.decode('utf-8')
    
    # Parse topic: opensentry/<camera_id>/status
    parts = topic.split('/')
    if len(parts) == 3 and parts[0] == 'opensentry' and parts[2] == 'status':
        camera_id = parts[1]
        
        # Only update status if camera is already registered via mDNS
        # MQTT is used for status updates and commands, not discovery
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
        _client.connect(MQTT_BROKER, MQTT_PORT, 60)
        _client.loop_start()
        print("[MQTT] Client started")
    except Exception as e:
        print(f"[MQTT] Initial connection failed: {e}")
        print("[MQTT] Will retry in background...")
        # Start loop anyway - it will auto-reconnect
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
