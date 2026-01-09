#!/bin/bash
# OpenSentry Command Center - Teardown Script
# Run: chmod +x teardown.sh && ./teardown.sh

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║         OpenSentry Command Center - Teardown                  ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Check if container is running
if docker ps -q -f name=opensentry-command-center | grep -q .; then
    echo "🛑 Stopping Command Center..."
    docker compose down
    echo "✅ Command Center stopped"
else
    echo "ℹ️  Command Center is not running"
fi

echo ""
read -p "Remove Docker image? This will require rebuild on next setup. (y/N): " remove_image
if [ "$remove_image" = "y" ] || [ "$remove_image" = "Y" ]; then
    echo "🗑️  Removing Docker image..."
    docker rmi opensentrycommand-opensentry-command 2>/dev/null || true
    echo "✅ Image removed"
fi

echo ""
read -p "Remove configuration (.env file)? (y/N): " remove_config
if [ "$remove_config" = "y" ] || [ "$remove_config" = "Y" ]; then
    rm -f .env
    echo "✅ Configuration removed"
fi

echo ""
read -p "Remove data and logs? (y/N): " remove_data
if [ "$remove_data" = "y" ] || [ "$remove_data" = "Y" ]; then
    rm -rf ./data ./logs
    echo "✅ Data and logs removed"
fi

echo ""
read -p "Remove SSL certificates? (y/N): " remove_certs
if [ "$remove_certs" = "y" ] || [ "$remove_certs" = "Y" ]; then
    rm -rf ./certs
    # Also remove from system trust store
    sudo rm -f /usr/local/share/ca-certificates/opensentry.crt 2>/dev/null
    sudo update-ca-certificates >/dev/null 2>&1 || true
    echo "✅ SSL certificates removed"
fi

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                  Teardown Complete!                           ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
echo "To set up again, run: ./setup.sh"
