"""
Authentication module for OpenSentry Command Center.
Uses Flask-Login with environment variable credentials.
Includes rate limiting to prevent brute force attacks.
"""
import os
import time
from functools import wraps
from collections import defaultdict

from flask import redirect, url_for, session, request
from flask_login import LoginManager, UserMixin, current_user
from werkzeug.security import check_password_hash, generate_password_hash

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access the Command Center.'
login_manager.login_message_category = 'info'

# Default credentials (override with environment variables)
DEFAULT_USERNAME = 'admin'
DEFAULT_PASSWORD = 'opensentry'

# Rate limiting configuration
MAX_FAILED_ATTEMPTS = 5  # Lock after 5 failed attempts
LOCKOUT_DURATION = 300   # 5 minutes lockout
ATTEMPT_WINDOW = 900     # Track attempts within 15 minute window

# Track failed login attempts: {ip: [(timestamp, ...], ...}
_failed_attempts = defaultdict(list)


class User(UserMixin):
    """Simple user class for Flask-Login"""
    def __init__(self, user_id, username):
        self.id = user_id
        self.username = username


# In-memory user store (single admin user)
_user = None


def get_credentials():
    """Get credentials from environment variables or use defaults"""
    username = os.environ.get('OPENSENTRY_USERNAME', DEFAULT_USERNAME)
    password = os.environ.get('OPENSENTRY_PASSWORD', DEFAULT_PASSWORD)
    return username, password


def init_app(app):
    """Initialize authentication for the Flask app"""
    # Set secret key from environment or use a default (change in production!)
    secret_key = os.environ.get('SECRET_KEY')
    if not secret_key:
        # Generate a stable default key based on credentials (not ideal for production)
        import hashlib
        username, password = get_credentials()
        secret_key = hashlib.sha256(f"opensentry-{username}-{password}".encode()).hexdigest()
    app.secret_key = secret_key
    
    # Initialize Flask-Login
    login_manager.init_app(app)
    
    # Create the admin user
    global _user
    username, _ = get_credentials()
    _user = User('1', username)
    
    print(f"[Auth] Authentication enabled for user: {username}")


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
        if current_time - t < ATTEMPT_WINDOW
    ]


def _record_failed_attempt(ip: str):
    """Record a failed login attempt"""
    _failed_attempts[ip].append(time.time())
    _clean_old_attempts(ip)
    print(f"[Auth] Failed login attempt from {ip} ({len(_failed_attempts[ip])}/{MAX_FAILED_ATTEMPTS})")


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
    
    if len(attempts) >= MAX_FAILED_ATTEMPTS:
        # Check if still in lockout period
        latest_attempt = max(attempts)
        time_since_lockout = time.time() - latest_attempt
        
        if time_since_lockout < LOCKOUT_DURATION:
            remaining = int(LOCKOUT_DURATION - time_since_lockout)
            return True, remaining
        else:
            # Lockout expired, clear attempts
            _clear_failed_attempts(ip)
    
    return False, 0


def get_client_ip() -> str:
    """Get the client IP address, handling proxies"""
    # Check for proxy headers
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    return request.remote_addr or '127.0.0.1'


def authenticate(username, password):
    """Authenticate a user with username and password (with rate limiting)"""
    ip = get_client_ip()
    
    # Check rate limiting
    limited, remaining = is_rate_limited(ip)
    if limited:
        print(f"[Auth] Rate limited login attempt from {ip} ({remaining}s remaining)")
        return None
    
    valid_username, valid_password = get_credentials()
    
    if username == valid_username and password == valid_password:
        _clear_failed_attempts(ip)
        print(f"[Auth] Successful login from {ip}")
        return _user
    
    # Record failed attempt
    _record_failed_attempt(ip)
    return None


def is_authenticated():
    """Check if the current user is authenticated"""
    return current_user.is_authenticated
