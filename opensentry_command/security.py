"""
Security middleware and utilities for OpenSentry Command Center.
Implements security headers, CSRF protection, and audit logging.
"""
import os
import secrets
import hashlib
from datetime import datetime
from pathlib import Path

from flask import request, session, g


# ============================================================================
# AUDIT LOGGING (Database Only)
# ============================================================================

def audit_log(event_type: str, ip: str, user: str = '-', details: str = ''):
    """Log a security-relevant event to database"""
    try:
        from flask import current_app
        from .models.database import AuditLog, db
        
        with current_app.app_context():
            log_entry = AuditLog(
                event=event_type,
                ip_address=ip,
                username=user if user != '-' else None,
                details=details
            )
            db.session.add(log_entry)
            db.session.commit()
    except Exception as e:
        # Log to console only as fallback during startup
        print(f"[Audit] {event_type} | {ip} | {user} | {details}")


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
