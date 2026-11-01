"""
Unit tests for security, password hashing, HMAC tokens, and rate limiting.
"""
from datetime import timedelta
import pytest

from admin_backend.security.passwords import hash_password, verify_password
from admin_backend.security.tokens import create_access_token, decode_access_token
from admin_backend.security.rate_limiter import InMemoryRateLimiter


def test_password_hashing_and_verification():
    raw_password = "SuperSecretPassword123!"
    hashed = hash_password(raw_password, iterations=10_000)  # fast iteration for test speed

    assert hashed.startswith("pbkdf2_sha256$10000$")
    assert verify_password(raw_password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password("", hashed) is False


def test_password_hash_tampering():
    raw = "ValidPassword123"
    hashed = hash_password(raw, iterations=5_000)
    # Tamper with the last character of the hash hex
    tampered = hashed[:-1] + ("0" if hashed[-1] != "0" else "1")
    assert verify_password(raw, tampered) is False


def test_token_creation_and_decoding():
    token = create_access_token(user_id="user-123", username="testadmin", role="admin")
    payload = decode_access_token(token)

    assert payload["sub"] == "user-123"
    assert payload["username"] == "testadmin"
    assert payload["role"] == "admin"
    assert "exp" in payload
    assert "jti" in payload


def test_token_expiration():
    # Create token expired 10 seconds ago
    token = create_access_token(
        user_id="user-123",
        username="testadmin",
        role="admin",
        expires_delta=timedelta(seconds=-10),
    )
    with pytest.raises(ValueError, match="expired"):
        decode_access_token(token)


def test_token_tampering():
    from admin_backend.security.tokens import _b64url_encode
    token = create_access_token(user_id="user-123", username="testadmin", role="admin")
    parts = token.split(".")
    # Tamper with signature using valid base64url data that does not match expected HMAC
    tampered_sig = parts[0] + "." + parts[1] + "." + _b64url_encode(b"invalid_tampered_hmac_signature")
    with pytest.raises(ValueError, match="verification failed"):
        decode_access_token(tampered_sig)


def test_rate_limiter_sliding_window():
    limiter = InMemoryRateLimiter(requests_per_minute=3)
    client_key = "127.0.0.1"

    allowed, rem = limiter.is_allowed(client_key)
    assert allowed is True
    assert rem == 2

    allowed, rem = limiter.is_allowed(client_key)
    assert allowed is True
    assert rem == 1

    allowed, rem = limiter.is_allowed(client_key)
    assert allowed is True
    assert rem == 0

    # 4th request exceeds limit
    allowed, rem = limiter.is_allowed(client_key)
    assert allowed is False
    assert rem == 0
