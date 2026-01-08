#!/usr/bin/env python3
"""
OpenSentry Command Center - Entry Point
"""
import os
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
    
    # Debug mode - disabled by default for security
    # Set DEBUG=true in environment to enable (development only!)
    debug_mode = os.environ.get('DEBUG', 'false').lower() == 'true'
    
    if debug_mode:
        print("[Flask] ⚠️  WARNING: Debug mode is ENABLED (not for production!)")
    
    # Start Flask web server
    print("[Flask] Starting web server on http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=debug_mode, threaded=True, use_reloader=False)


if __name__ == '__main__':
    main()
