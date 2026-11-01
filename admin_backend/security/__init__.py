"""
Security module for admin backend:
- Passwords (PBKDF2-HMAC-SHA256)
- Signed Tokens (HS256)
- Role-based Access Control (RBAC)
- Rate limiting
- Destructive confirmation checks
"""

from admin_backend.security.passwords import hash_password, verify_password
from admin_backend.security.tokens import create_access_token, decode_access_token
from admin_backend.security.dependencies import (
    get_current_user,
    require_admin_role,
    require_user_role,
    require_destructive_confirmation,
)

__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "decode_access_token",
    "get_current_user",
    "require_admin_role",
    "require_user_role",
    "require_destructive_confirmation",
]
