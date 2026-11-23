"""
Regular User Authentication Package.
Provides email/password and Google OAuth authentication for regular users.
Uses opaque random session tokens stored as SHA-256 hashes in user_sessions_v2,
delivered via httpOnly cookies. Completely separated from admin backend authentication.
"""

