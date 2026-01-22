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
login_manager.login_view = "main.login"
login_manager.login_message = "Please log in to access the Command Center."
login_manager.login_message_category = "info"

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
        admin_count = User.query.filter_by(role="admin").count()
        total_users = User.query.count()

        # Check if default admin is using default password
        admin = User.query.filter_by(username="admin").first()
        if admin and admin.check_password("opensentry"):
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
        print(
            f"[Auth] Rate limiting: {Config.MAX_FAILED_ATTEMPTS} attempts / {Config.ATTEMPT_WINDOW}s window"
        )


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login"""
    from ..models.database import User

    return User.query.get(int(user_id))


def get_client_ip() -> str:
    """Get the client IP address, handling proxies"""
    if request.headers.get("X-Forwarded-For"):
        return request.headers.get("X-Forwarded-For").split(",")[0].strip()
    elif request.headers.get("X-Real-IP"):
        return request.headers.get("X-Real-IP")
    return request.remote_addr or "127.0.0.1"


def authenticate(username: str, password: str):
    """Authenticate a user with username and password (with database-backed rate limiting)"""
    from ..models.database import User, db, RateLimit

    ip = get_client_ip()

    # Check rate limiting using database
    is_limited, remaining = RateLimit.is_locked(ip)
    if is_limited:
        audit_log("LOGIN_RATE_LIMITED", ip, username, f"Locked out for {remaining}s")
        return None

    # Look up user in database
    user = User.query.filter_by(username=username).first()

    if user and user.is_active and user.check_password(password):
        RateLimit.clear_attempts(ip)
        # Update last login time
        user.last_login = datetime.utcnow()
        db.session.commit()
        audit_log(
            "LOGIN_SUCCESS",
            ip,
            username,
            f"Authentication successful (role: {user.role})",
        )
        return user

    # Record failed attempt in database
    attempts, lockout = RateLimit.record_failed_attempt(
        ip,
        window_seconds=Config.ATTEMPT_WINDOW,
        max_attempts=Config.MAX_FAILED_ATTEMPTS,
        lockout_seconds=Config.LOCKOUT_DURATION,
    )

    if lockout:
        audit_log(
            "LOGIN_LOCKED_OUT", ip, username, f"Locked out after {attempts} attempts"
        )
    else:
        audit_log(
            "LOGIN_FAILURE",
            ip,
            username,
            f"Invalid credentials (attempt {attempts}/{Config.MAX_FAILED_ATTEMPTS})",
        )

    return None


def is_using_defaults() -> bool:
    """Check if system is using default credentials"""
    return _using_default_credentials


def log_logout(username: str):
    """Log a logout event"""
    ip = get_client_ip()
    audit_log("LOGOUT", ip, username, "User logged out")


def is_authenticated():
    """Check if the current user is authenticated"""
    return current_user.is_authenticated
