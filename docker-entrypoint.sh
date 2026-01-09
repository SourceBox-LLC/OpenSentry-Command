#!/bin/bash
set -e

# Start D-Bus daemon (required for Avahi)
echo "[OpenSentry Command] Starting D-Bus..."
mkdir -p /var/run/dbus
dbus-daemon --system --fork 2>/dev/null || true
sleep 1

# Start Avahi daemon for mDNS discovery
echo "[OpenSentry Command] Starting Avahi for mDNS discovery..."
mkdir -p /var/run/avahi-daemon
avahi-daemon -D 2>/dev/null || echo "[Warning] Avahi daemon failed to start - mDNS discovery may not work"
sleep 1

# Generate SSL certificates if they don't exist
CERT_DIR="/app/certs"
CERT_FILE="$CERT_DIR/server.crt"
KEY_FILE="$CERT_DIR/server.key"

if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
    echo "[OpenSentry Command] 🔐 Generating SSL certificates..."
    mkdir -p "$CERT_DIR"
    
    # Generate self-signed certificate valid for 365 days
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$KEY_FILE" \
        -out "$CERT_FILE" \
        -subj "/C=US/ST=Local/L=Local/O=OpenSentry/OU=Security/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,DNS:opensentry,DNS:opensentry.local,IP:127.0.0.1" \
        2>/dev/null
    
    chmod 600 "$KEY_FILE"
    chmod 644 "$CERT_FILE"
    echo "[OpenSentry Command] ✅ SSL certificates generated"
else
    echo "[OpenSentry Command] ✅ SSL certificates found"
fi

echo "[OpenSentry Command] Starting Command Center..."

# Execute the main command
exec "$@"
