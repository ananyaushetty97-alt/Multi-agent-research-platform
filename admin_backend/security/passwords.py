"""
Secure password hashing using PBKDF2-HMAC-SHA256.
Standard library implementation (OWASP compliant with 600,000 iterations)
with constant-time verification to prevent timing attacks.
Requires zero external C-dependencies or additional packages.
"""
import hashlib
import hmac
import secrets

DEFAULT_ITERATIONS = 600_000
SALT_BYTES = 16
ALGORITHM = "pbkdf2_sha256"


def hash_password(plain_password: str, iterations: int = DEFAULT_ITERATIONS) -> str:
    """
    Hash a password using PBKDF2-HMAC-SHA256 with a unique random salt.
    Returns: pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>
    """
    if not plain_password:
        raise ValueError("Password cannot be empty")

    salt = secrets.token_bytes(SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        plain_password.encode("utf-8"),
        salt,
        iterations
    )
    return f"{ALGORITHM}${iterations}${salt.hex()}${derived.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain password against a stored hash using constant-time comparison.
    """
    if not plain_password or not hashed_password:
        return False

    try:
        parts = hashed_password.split("$")
        if len(parts) != 4 or parts[0] != ALGORITHM:
            return False

        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected_hash = bytes.fromhex(parts[3])

        candidate_hash = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt,
            iterations
        )
        return hmac.compare_digest(candidate_hash, expected_hash)
    except (ValueError, TypeError):
        return False
