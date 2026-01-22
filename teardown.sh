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
read -p "Remove database (users, media, audit logs)? (y/N): " remove_data
if [ "$remove_data" = "y" ] || [ "$remove_data" = "Y" ]; then
    echo "🗑️  Removing database..."
    if sudo rm -rf ./data 2>/dev/null; then
        echo "✅ Database removed"
    else
        if [ ! -d "./data" ]; then
            echo "✅ Database removed (already gone)"
        else
            echo "⚠️  Could not remove database. Check permissions in ./data/"
        fi
    fi
fi

echo ""
read -p "Remove SSL certificates? (y/N): " remove_certs
if [ "$remove_certs" = "y" ] || [ "$remove_certs" = "Y" ]; then
    echo "🗑️  Removing SSL certificates..."

    # Try removing directly first
    if rm -rf ./certs 2>/dev/null; then
        echo "✅ SSL certificates removed"
    else
        # Permission denied - try with sudo
        echo "⚠️  Permission denied. Trying with sudo..."
        if sudo rm -rf ./certs 2>/dev/null; then
            echo "✅ SSL certificates removed (with sudo)"
        else
            # Still failed - maybe certs don't exist or other issue
            if [ ! -d "./certs" ]; then
                echo "✅ SSL certificates removed (already gone)"
            else
                echo "⚠️  Could not remove certificates. Check permissions in ./certs/"
            fi
        fi
    fi

    # Also remove from system trust store
    echo "🔐 Removing from system trust store..."
    if sudo rm -f /usr/local/share/ca-certificates/opensentry.crt 2>/dev/null; then
        sudo update-ca-certificates >/dev/null 2>&1 || true
        echo "✅ Removed from system trust store"
    else
        echo "ℹ️  No certificate found in system trust store"
    fi
fi

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║                  Teardown Complete!                           ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
echo "To set up again, run: ./setup.sh"
