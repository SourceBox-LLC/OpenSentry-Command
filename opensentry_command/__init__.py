"""
OpenSentry Command Center - Flask Application Factory
"""
import signal
import atexit

from flask import Flask

from .config import Config
from .security import (
    add_security_headers,
    generate_csrf_token,
    configure_session_security,
    generate_secret_key
)


def create_app(config_class=Config):
    """Application factory pattern for Flask app creation"""
    app = Flask(__name__,
                static_folder='static',
                template_folder='templates')
    
    # Load configuration
    app.config.from_object(config_class)
    
    # Generate proper secret key if not set
    if not app.config.get('SECRET_KEY'):
        app.config['SECRET_KEY'] = generate_secret_key()
    
    # Configure session security
    configure_session_security(app)
    
    # Add security headers to all responses
    app.after_request(add_security_headers)
    
    # Make CSRF token available in all templates
    app.jinja_env.globals['csrf_token'] = generate_csrf_token
    
    # Initialize extensions
    from .auth import init_auth
    init_auth(app)
    
    # Register blueprints
    from .routes import main_bp, api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Register cleanup handlers
    from .services import mqtt, discovery
    
    def cleanup():
        """Graceful shutdown - stop all services"""
        print("\n[System] Shutting down...")
        
        from .models.camera import camera_streams
        for camera_id, stream in camera_streams.items():
            print(f"[System] Stopping camera {camera_id}...")
            stream.stop()
        
        mqtt.stop()
        discovery.stop_discovery()
        print("[System] Shutdown complete")
    
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, lambda s, f: exit(0))
    signal.signal(signal.SIGTERM, lambda s, f: exit(0))
    
    return app
