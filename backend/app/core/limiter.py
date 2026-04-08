from slowapi import Limiter
from slowapi.util import get_remote_address

# Shared rate limiter — keyed by client IP address.
# Import this in any router module that needs rate limiting.
limiter = Limiter(key_func=get_remote_address)
