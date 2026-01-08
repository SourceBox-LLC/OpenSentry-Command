"""
OpenSentry Command Center - Flask Application Factory
"""
import signal
import atexit

from flask import Flask

from .config import Config


def create_app(config_class=Config):
    """Application factory pattern for Flask app creation"""
    app = Flask(__name__,
                static_folder='static',
                template_folder='templates')
    
    # Load configuration
    app.config.from_object(config_class)
    
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
