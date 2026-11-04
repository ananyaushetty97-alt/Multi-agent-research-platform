"""
Cryptographic token generation and verification using HMAC-SHA256.
Compliant with JWT format without requiring external dependencies (PyJWT/python-jose).
Includes expiration checking, tampering defense, and constant-time signature verification.
"""
import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from admin_backend.config import settings


def _b64url_encode(data: bytes) -> str:
    """Base64 URL-safe encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    """Base64 URL-safe decode with padding restoration."""
    rem = len(s) % 4
    if rem > 0:
        s += "=" * (4 - rem)
    return base64.urlsafe_b64decode(s.encode("ascii"))


def create_access_token(
    user_id: str,
    username: str,
    role: str,
    expires_delta: timedelta | None = None
) -> str:
    """
    Generate an HMAC-SHA256 signed access token.
    """
    now = datetime.now(timezone.utc)
    delta = expires_delta or timedelta(minutes=settings.admin_token_expire_minutes)
    exp = now + delta

    header = {
        "alg": settings.admin_token_algorithm,
        "typ": "JWT"
    }
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": str(uuid.uuid4())
    }

    header_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    signing_input = f"{_b64url_encode(header_bytes)}.{_b64url_encode(payload_bytes)}".encode("utf-8")
    key = settings.get_signing_key()
    signature = hmac.new(key, signing_input, hashlib.sha256).digest()

    return f"{signing_input.decode('utf-8')}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Validate and decode a signed token.
    Raises ValueError if token is expired, tampered with, or malformed.
    """
    if not token or not isinstance(token, str):
        raise ValueError("Token must be a non-empty string")

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed token: must contain 3 segments")

    header_b64, payload_b64, signature_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")

    key = settings.get_signing_key()
    expected_sig = hmac.new(key, signing_input, hashlib.sha256).digest()

    try:
        given_sig = _b64url_decode(signature_b64)
    except Exception:
        raise ValueError("Invalid token signature encoding")

    if not hmac.compare_digest(expected_sig, given_sig):
        raise ValueError("Token signature verification failed")

    try:
        payload_bytes = _b64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        raise ValueError("Invalid token payload")

    # Expiration check
    exp = payload.get("exp")
    if not exp or not isinstance(exp, (int, float)):
        raise ValueError("Token missing expiration claim")

    now = int(time.time())
    if now > exp:
        raise ValueError("Token has expired")

    return payload
