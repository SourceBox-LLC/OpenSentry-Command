#!/usr/bin/env python3
"""
OpenSentry Command Center - Entry Point
"""
import os
import ssl
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
    
    # Check for HTTPS certificates
    https_enabled = os.environ.get('HTTPS_ENABLED', 'true').lower() == 'true'
    cert_file = '/app/certs/server.crt'
    key_file = '/app/certs/server.key'
    
    # Fallback to local certs directory for non-Docker runs
    if not os.path.exists(cert_file):
        cert_file = os.path.join(os.path.dirname(__file__), 'certs', 'server.crt')
        key_file = os.path.join(os.path.dirname(__file__), 'certs', 'server.key')
    
    if https_enabled and os.path.exists(cert_file) and os.path.exists(key_file):
        # HTTPS mode
        print("[Flask] 🔒 Starting HTTPS web server on https://0.0.0.0:5000")
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
        ssl_context.load_cert_chain(cert_file, key_file)
        app.run(host='0.0.0.0', port=5000, debug=debug_mode, threaded=True, 
                use_reloader=False, ssl_context=ssl_context)
    else:
        # HTTP mode (fallback)
        if https_enabled:
            print("[Flask] ⚠️  WARNING: HTTPS enabled but certificates not found!")
            print("[Flask] ⚠️  Falling back to HTTP (insecure)")
        print("[Flask] Starting web server on http://0.0.0.0:5000")
        app.run(host='0.0.0.0', port=5000, debug=debug_mode, threaded=True, use_reloader=False)


if __name__ == '__main__':
    main()
