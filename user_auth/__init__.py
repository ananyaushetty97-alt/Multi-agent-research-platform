"""
Regular User Authentication Package.
Provides email/password and Google OAuth authentication for regular users.
Uses opaque random session tokens stored as SHA-256 hashes in user_sessions,
delivered via httpOnly cookies. Completely separated from admin backend authentication.
"""
from user_auth.routes import router

__all__ = ["router"]
