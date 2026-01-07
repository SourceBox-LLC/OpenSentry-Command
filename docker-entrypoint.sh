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

echo "[OpenSentry Command] Starting Command Center..."

# Execute the main command
exec "$@"
