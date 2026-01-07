"""
Authentication module for OpenSentry Command Center.
Uses Flask-Login with environment variable credentials.
"""
import os
from functools import wraps

from flask import redirect, url_for, session
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


def authenticate(username, password):
    """Authenticate a user with username and password"""
    valid_username, valid_password = get_credentials()
    
    if username == valid_username and password == valid_password:
        return _user
    return None


def is_authenticated():
    """Check if the current user is authenticated"""
    return current_user.is_authenticated
