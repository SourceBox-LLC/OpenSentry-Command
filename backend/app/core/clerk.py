from clerk_backend_api import Clerk

from app.core.config import settings

if not settings.CLERK_SECRET_KEY:
    raise ValueError("CLERK_SECRET_KEY is required. Please set it in your .env file.")

clerk = Clerk(bearer_auth=settings.CLERK_SECRET_KEY)
