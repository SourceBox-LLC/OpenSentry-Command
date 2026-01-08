#!/usr/bin/env python3
"""
OpenSentry Command Center - Entry Point
"""
from dotenv import load_dotenv

# Load environment variables before importing app
load_dotenv()

from opensentry_command import create_app
from opensentry_command.services import mqtt, discovery


def main():
    """Main entry point"""
    app = create_app()
    
    # Start background services
    mqtt.start()
    discovery.start_discovery()
    
    # Start Flask web server
    print("[Flask] Starting web server on http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True, use_reloader=False)


if __name__ == '__main__':
    main()
