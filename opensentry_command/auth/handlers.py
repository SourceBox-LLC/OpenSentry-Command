"""
Authentication handlers for OpenSentry Command Center.
Uses Flask-Login with database-backed users.
Includes rate limiting to prevent brute force attacks.
Includes session timeout for security.
Includes audit logging for security events.
"""
import time
from datetime import datetime
from collections import defaultdict

from flask import request
from flask_login import LoginManager, current_user

from ..config import Config
from ..security import audit_log, is_using_default_credentials

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.login_view = 'main.login'
login_manager.login_message = 'Please log in to access the Command Center.'
login_manager.login_message_category = 'info'

# Track failed login attempts: {ip: [timestamps]}
_failed_attempts = defaultdict(list)

# Flag for default credentials warning
_using_default_credentials = False


def init_auth(app):
    """Initialize authentication for the Flask app"""
    global _using_default_credentials
    
    # Initialize Flask-Login
    login_manager.init_app(app)
    
    # Import User model here to avoid circular imports
    from ..models.database import User, db
    
    with app.app_context():
        # Get admin user count
        admin_count = User.query.filter_by(role='admin').count()
        total_users = User.query.count()
        
        # Check if default admin is using default password
        admin = User.query.filter_by(username='admin').first()
        if admin and admin.check_password('opensentry'):
            _using_default_credentials = True
            print("\n" + "=" * 70)
            print("⚠️  WARNING: DEFAULT CREDENTIALS DETECTED!")
            print("=" * 70)
            print("The admin account is using the default password.")
            print("This is a SECURITY RISK. Change it in Settings > User Management")
            print("=" * 70 + "\n")
        
        print(f"[Auth] Database authentication enabled")
        print(f"[Auth] Users: {total_users} total, {admin_count} admin(s)")
        print(f"[Auth] Session timeout: {Config.SESSION_TIMEOUT_MINUTES} minutes")


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login"""
    from ..models.database import User
    return User.query.get(int(user_id))


def _clean_old_attempts(ip: str):
    """Remove attempts older than the tracking window"""
    current_time = time.time()
    _failed_attempts[ip] = [
        t for t in _failed_attempts[ip] 
        if current_time - t < Config.ATTEMPT_WINDOW
    ]


def _record_failed_attempt(ip: str):
    """Record a failed login attempt"""
    _failed_attempts[ip].append(time.time())
    _clean_old_attempts(ip)
    print(f"[Auth] Failed login attempt from {ip} ({len(_failed_attempts[ip])}/{Config.MAX_FAILED_ATTEMPTS})")


def _clear_failed_attempts(ip: str):
    """Clear failed attempts after successful login"""
    if ip in _failed_attempts:
        del _failed_attempts[ip]


def is_rate_limited(ip: str) -> tuple[bool, int]:
    """
    Check if an IP is rate limited.
    Returns (is_limited, seconds_remaining)
    """
    _clean_old_attempts(ip)
    attempts = _failed_attempts.get(ip, [])
    
    if len(attempts) >= Config.MAX_FAILED_ATTEMPTS:
        latest_attempt = max(attempts)
        time_since_lockout = time.time() - latest_attempt
        
        if time_since_lockout < Config.LOCKOUT_DURATION:
            remaining = int(Config.LOCKOUT_DURATION - time_since_lockout)
            return True, remaining
        else:
            _clear_failed_attempts(ip)
    
    return False, 0


def get_client_ip() -> str:
    """Get the client IP address, handling proxies"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    return request.remote_addr or '127.0.0.1'


def authenticate(username: str, password: str):
    """Authenticate a user with username and password (with rate limiting)"""
    from ..models.database import User, db
    
    ip = get_client_ip()
    
    # Check rate limiting
    limited, remaining = is_rate_limited(ip)
    if limited:
        audit_log('LOGIN_RATE_LIMITED', ip, username, f'Locked out for {remaining}s')
        return None
    
    # Look up user in database
    user = User.query.filter_by(username=username).first()
    
    if user and user.is_active and user.check_password(password):
        _clear_failed_attempts(ip)
        # Update last login time
        user.last_login = datetime.utcnow()
        db.session.commit()
        audit_log('LOGIN_SUCCESS', ip, username, f'Authentication successful (role: {user.role})')
        return user
    
    _record_failed_attempt(ip)
    attempts = len(_failed_attempts.get(ip, []))
    audit_log('LOGIN_FAILURE', ip, username, f'Invalid credentials (attempt {attempts}/{Config.MAX_FAILED_ATTEMPTS})')
    return None


def is_using_defaults() -> bool:
    """Check if system is using default credentials"""
    return _using_default_credentials


def log_logout(username: str):
    """Log a logout event"""
    ip = get_client_ip()
    audit_log('LOGOUT', ip, username, 'User logged out')


def is_authenticated():
    """Check if the current user is authenticated"""
    return current_user.is_authenticated
