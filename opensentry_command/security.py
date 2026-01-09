"""
Security middleware and utilities for OpenSentry Command Center.
Implements security headers, CSRF protection, and audit logging.
"""
import os
import secrets
import hashlib
import logging
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import request, session, abort, g


# ============================================================================
# AUDIT LOGGING
# ============================================================================

# Setup audit logger
_audit_logger = None


def _get_audit_logger():
    """Get or create the audit logger"""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = logging.getLogger('opensentry.audit')
        _audit_logger.setLevel(logging.INFO)
        
        # Create logs directory if it doesn't exist
        log_dir = Path('/var/log/opensentry')
        if not log_dir.exists():
            # Fall back to local directory
            log_dir = Path(__file__).parent.parent / 'logs'
            log_dir.mkdir(exist_ok=True)
        
        # File handler for audit log
        audit_file = log_dir / 'audit.log'
        file_handler = logging.FileHandler(audit_file)
        file_handler.setLevel(logging.INFO)
        
        # Format: timestamp | event_type | ip | user | details
        formatter = logging.Formatter(
            '%(asctime)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        _audit_logger.addHandler(file_handler)
        
        # Also log to console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter('[Audit] %(message)s'))
        _audit_logger.addHandler(console_handler)
        
        print(f"[Security] Audit logging enabled: {audit_file}")
    
    return _audit_logger


def audit_log(event_type: str, ip: str, user: str = '-', details: str = ''):
    """Log a security-relevant event"""
    logger = _get_audit_logger()
    logger.info(f"{event_type} | {ip} | {user} | {details}")


# ============================================================================
# CSRF PROTECTION
# ============================================================================

def generate_csrf_token():
    """Generate a CSRF token and store in session"""
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


def validate_csrf_token():
    """Validate CSRF token from form submission"""
    token = session.get('_csrf_token')
    form_token = request.form.get('_csrf_token')
    
    if not token or not form_token:
        return False
    
    return secrets.compare_digest(token, form_token)


def csrf_protect(f):
    """Decorator to enforce CSRF protection on POST requests"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            if not validate_csrf_token():
                audit_log('CSRF_FAILURE', _get_request_ip(), details='Invalid CSRF token')
                abort(403, description='CSRF token validation failed')
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# SECURITY HEADERS
# ============================================================================

def add_security_headers(response):
    """Add security headers to response"""
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'DENY'
    
    # Prevent MIME type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    
    # XSS protection (legacy browsers)
    response.headers['X-XSS-Protection'] = '1; mode=block'
    
    # Referrer policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    
    # Permissions policy (disable unnecessary features)
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    
    # Content Security Policy
    # Allow inline styles for our UI, restrict everything else
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "base-uri 'self';"
    )
    response.headers['Content-Security-Policy'] = csp
    
    # Cache control for authenticated pages
    if request.endpoint and 'login' not in request.endpoint:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, private'
        response.headers['Pragma'] = 'no-cache'
    
    return response


# ============================================================================
# SECRET KEY GENERATION
# ============================================================================

def generate_secret_key():
    """Generate a cryptographically secure secret key"""
    # Try to use a persistent secret key file
    secret_file = Path(__file__).parent.parent / '.secret_key'
    
    if secret_file.exists():
        return secret_file.read_text().strip()
    
    # Generate new secret key
    secret_key = secrets.token_hex(32)
    
    # Try to persist it
    try:
        secret_file.write_text(secret_key)
        secret_file.chmod(0o600)  # Owner read/write only
        print(f"[Security] Generated new secret key (saved to {secret_file})")
    except (IOError, OSError):
        print("[Security] Generated ephemeral secret key (could not persist)")
    
    return secret_key


# ============================================================================
# DEFAULT CREDENTIAL CHECK
# ============================================================================

# Default credentials that should never be used in production
DEFAULT_CREDENTIALS = [
    ('admin', 'admin'),
    ('admin', 'password'),
    ('admin', 'opensentry'),
    ('opensentry', 'opensentry'),
    ('root', 'root'),
    ('user', 'user'),
]


def is_using_default_credentials(username: str, password: str) -> bool:
    """Check if the provided credentials are known defaults"""
    return (username.lower(), password) in DEFAULT_CREDENTIALS


def check_credential_strength(password: str) -> tuple[bool, str]:
    """
    Check password strength.
    Returns (is_acceptable, message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    
    # Check for basic complexity (at least one letter and one number)
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    
    if not (has_letter and has_digit):
        return False, "Password should contain letters and numbers"
    
    return True, "OK"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _get_request_ip() -> str:
    """Get client IP from request"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    return request.remote_addr or '127.0.0.1'


# ============================================================================
# SESSION SECURITY
# ============================================================================

def configure_session_security(app):
    """Configure secure session settings"""
    # Session cookie settings
    https_enabled = os.environ.get('HTTPS_ENABLED', 'true').lower() == 'true'
    app.config['SESSION_COOKIE_SECURE'] = https_enabled
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_NAME'] = 'opensentry_session'
    
    if https_enabled:
        print("[Security] 🔒 HTTPS mode: Secure cookies enabled")
    else:
        print("[Security] ⚠️  HTTP mode: Cookies not marked secure")
    print(f"[Security] Session cookies: HttpOnly=True, SameSite=Lax, Secure={app.config['SESSION_COOKIE_SECURE']}")
