"""
Authentication handlers for OpenSentry Command Center.
Uses Flask-Login with environment variable credentials.
Includes rate limiting to prevent brute force attacks.
Includes session timeout for security.
Includes audit logging for security events.
"""
import time
from collections import defaultdict

from flask import request
from flask_login import LoginManager, UserMixin, current_user

from ..config import Config
from ..security import audit_log, is_using_default_credentials

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.login_view = 'main.login'
login_manager.login_message = 'Please log in to access the Command Center.'
login_manager.login_message_category = 'info'

# Track failed login attempts: {ip: [timestamps]}
_failed_attempts = defaultdict(list)

# In-memory user store (single admin user)
_user = None

# Flag for default credentials warning
_using_default_credentials = False


class User(UserMixin):
    """Simple user class for Flask-Login"""
    def __init__(self, user_id, username):
        self.id = user_id
        self.username = username


def init_auth(app):
    """Initialize authentication for the Flask app"""
    global _using_default_credentials
    
    # Initialize Flask-Login
    login_manager.init_app(app)
    
    # Create the admin user
    global _user
    _user = User('1', Config.OPENSENTRY_USERNAME)
    
    # Check for default credentials
    _using_default_credentials = is_using_default_credentials(
        Config.OPENSENTRY_USERNAME, 
        Config.OPENSENTRY_PASSWORD
    )
    
    if _using_default_credentials:
        print("\n" + "=" * 70)
        print("⚠️  WARNING: DEFAULT CREDENTIALS DETECTED!")
        print("=" * 70)
        print("You are using default username/password.")
        print("This is a SECURITY RISK. Please change your credentials in .env:")
        print("  OPENSENTRY_USERNAME=your_username")
        print("  OPENSENTRY_PASSWORD=your_secure_password")
        print("=" * 70 + "\n")
    
    print(f"[Auth] Authentication enabled for user: {Config.OPENSENTRY_USERNAME}")
    print(f"[Auth] Session timeout: {Config.SESSION_TIMEOUT_MINUTES} minutes")


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login"""
    if _user and _user.id == user_id:
        return _user
    return None


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
    ip = get_client_ip()
    
    # Check rate limiting
    limited, remaining = is_rate_limited(ip)
    if limited:
        audit_log('LOGIN_RATE_LIMITED', ip, username, f'Locked out for {remaining}s')
        return None
    
    if username == Config.OPENSENTRY_USERNAME and password == Config.OPENSENTRY_PASSWORD:
        _clear_failed_attempts(ip)
        audit_log('LOGIN_SUCCESS', ip, username, 'Authentication successful')
        return _user
    
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
