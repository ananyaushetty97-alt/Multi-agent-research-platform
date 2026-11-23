"""
Comprehensive tests for user_auth module:
- Password validation and PBKDF2 hashing
- Session management, cookie lifecycle, and revocation
- Google OAuth account creation, linking, and session revocation
- Multi-layer CSRF defense (Origin/Host + X-Requested-With)
- CORS credential security assertions
- Lockout and rate limiting
- 503 fail-fast handling
- Admin and regular user structural isolation
"""
import os
import unittest.mock

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from starlette.middleware.cors import CORSMiddleware

from api.main import app
from user_auth.config import settings
from user_auth.models import UserRegisterRequest, UserLoginRequest
from user_auth.security import auth_security_manager
from user_auth.service import UserAuthService, auth_service
from user_auth.storage import InMemoryUserAuthStorage, set_user_auth_storage


@pytest.fixture(autouse=True)
def setup_in_memory_auth(monkeypatch):
    """Inject fresh in-memory storage for each test."""
    mem_storage = InMemoryUserAuthStorage()
    set_user_auth_storage(mem_storage)
    auth_service._storage_override = mem_storage
    auth_security_manager.reset()
    settings.auth_storage_backend = "memory"
    settings.neutralize_demo_users = True
    settings.require_login = False
    monkeypatch.setattr(settings, "smtp_host", None)
    monkeypatch.setattr(settings, "resend_api_key", None)
    monkeypatch.setattr(settings, "brevo_api_key", None)

    try:
        import psycopg
        monkeypatch.setattr(psycopg, "connect", unittest.mock.MagicMock(side_effect=psycopg.OperationalError("PostgreSQL offline for unit test")))
    except ImportError:
        pass

    # Also inject InMemoryUserStorage for admin auth routes so tests run fast offline
    from admin_backend.storage.in_memory import InMemoryUserStorage
    from admin_backend.security.passwords import hash_password
    from admin_backend.routes import auth_routes
    from admin_backend.services.audit_service import audit_service
    from admin_backend.config import settings as admin_settings
    import tempfile

    class InMemoryAuditStorageForTests:
        def __init__(self):
            self.audit_entries = []
            self.user_activity_entries = []
        def append_audit_entry(self, entry):
            self.audit_entries.append(entry)
        def append_user_activity_entry(self, entry):
            self.user_activity_entries.append(entry)
        def query_audit_entries(self, filter_opts):
            return list(self.audit_entries)
        def query_user_activity_entries(self, filter_opts):
            return list(self.user_activity_entries)

    monkeypatch.setattr(audit_service, "storage", InMemoryAuditStorageForTests())
    temp_audit_file = os.path.join(tempfile.mkdtemp(), "test_user_auth_audit.jsonl")
    monkeypatch.setattr(audit_service, "log_file", temp_audit_file)
    monkeypatch.setattr(admin_settings, "admin_audit_log_path", temp_audit_file)

    admin_mem = InMemoryUserStorage()
    hashed_admin = hash_password("admin123", iterations=50_000)
    admin_mem.create_user({
        "id": "admin-1",
        "username": "admin",
        "email": "admin@platform.ai",
        "hashed_password": hashed_admin,
        "role": "admin",
        "is_active": True,
    })
    monkeypatch.setattr(auth_routes, "user_storage", admin_mem)

    yield mem_storage
    auth_security_manager.reset()


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. CSRF & CORS Tests (Condition 6)
# ---------------------------------------------------------------------------
def test_cors_allow_credentials_is_not_enabled():
    """Assert that allow_credentials is NOT enabled on wildcard CORS middleware."""
    cors_found = False
    for m in app.user_middleware:
        if m.cls == CORSMiddleware:
            cors_found = True
            # allow_credentials must be False when allow_origins=["*"]
            assert not m.kwargs.get("allow_credentials", False)
    assert cors_found, "CORSMiddleware must be configured on app"


def test_csrf_missing_custom_header_returns_403(client):
    """State-changing auth endpoints must reject requests missing X-Requested-With with 403."""
    resp = client.post("/api/auth/register", json={
        "name": "Alice Researcher",
        "email": "alice@example.com",
        "password": "Password123",
        "confirm_password": "Password123"
    })
    assert resp.status_code == 403
    assert "Missing or invalid X-Requested-With header" in resp.json()["detail"]


def test_csrf_mismatched_origin_returns_403(client):
    """Requests with an untrusted Origin header must be rejected with 403."""
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "http://evil-attacker.com",
        "Host": "localhost:8000"
    }
    resp = client.post("/api/auth/login", json={
        "email": "alice@example.com",
        "password": "Password123"
    }, headers=headers)
    assert resp.status_code == 403
    assert "Origin mismatch" in resp.json()["detail"]


def test_csrf_valid_origin_and_header_passes(client):
    """Valid Origin matching Host and X-Requested-With header passes CSRF verification."""
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "http://localhost:8000",
        "Host": "localhost:8000"
    }
    resp = client.post("/api/auth/login", json={
        "email": "alice@example.com",
        "password": "Password123"
    }, headers=headers)
    # Passed CSRF check; reached authentication logic (which returns 401 for unknown user)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 2. Registration & Password Tests (Condition 2, 4, 11)
# ---------------------------------------------------------------------------
def test_register_success(client):
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "http://localhost:8000",
        "Host": "localhost:8000"
    }
    resp = client.post("/api/auth/register", json={
        "name": "Alice Scholar",
        "email": "Alice.Scholar@Example.COM",
        "password": "ValidPassword123",
        "confirm_password": "ValidPassword123"
    }, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == "alice.scholar@example.com"
    assert data["full_name"] == "Alice Scholar"
    assert data["role"] == "user"
    assert not data["email_verified"]

    # In email verification flow, NO session cookie is issued until OTP is verified
    assert settings.session_cookie_name not in resp.cookies


def test_register_duplicate_email_rejected(client):
    headers = {"X-Requested-With": "XMLHttpRequest"}
    req = {
        "name": "Alice Scholar",
        "email": "alice@example.com",
        "password": "ValidPassword123",
        "confirm_password": "ValidPassword123"
    }
    r1 = client.post("/api/auth/register", json=req, headers=headers)
    assert r1.status_code == 200

    # Second attempt with same email (different case)
    req["email"] = "ALICE@EXAMPLE.COM"
    r2 = client.post("/api/auth/register", json=req, headers=headers)
    assert r2.status_code == 409
    assert "An account with this email already exists" in r2.json()["detail"]


def test_register_password_complexity(client):
    headers = {"X-Requested-With": "XMLHttpRequest"}
    # Missing digit
    r1 = client.post("/api/auth/register", json={
        "name": "Alice", "email": "a1@example.com", "password": "NoDigitsInPassword", "confirm_password": "NoDigitsInPassword"
    }, headers=headers)
    assert r1.status_code == 422

    # Too short (<8)
    r2 = client.post("/api/auth/register", json={
        "name": "Alice", "email": "a2@example.com", "password": "Pass1", "confirm_password": "Pass1"
    }, headers=headers)
    assert r2.status_code == 422

    # Password mismatch
    r3 = client.post("/api/auth/register", json={
        "name": "Alice", "email": "a3@example.com", "password": "Password123", "confirm_password": "Password456"
    }, headers=headers)
    assert r3.status_code == 422


# ---------------------------------------------------------------------------
# 3. Login, Lockout & Verification Order Tests (Condition 1, 2, 10)
# ---------------------------------------------------------------------------
def test_login_success(client):
    headers = {"X-Requested-With": "XMLHttpRequest"}
    # Register first
    client.post("/api/auth/register", json={
        "name": "Bob Scholar",
        "email": "bob@example.com",
        "password": "Password123",
        "confirm_password": "Password123"
    }, headers=headers)

    # Unverified user cannot log in
    unverified_resp = client.post("/api/auth/login", json={
        "email": "BOB@example.com",
        "password": "Password123"
    }, headers=headers)
    assert unverified_resp.status_code == 403
    assert "verification" in unverified_resp.json()["detail"].lower()

    # Manually mark verified or verify via OTP
    storage = auth_service.storage
    user = storage.get_user_by_email("bob@example.com")
    storage.update_user(user["id"], {"email_verified": True})

    # Verified login succeeds
    resp = client.post("/api/auth/login", json={
        "email": "BOB@example.com",
        "password": "Password123"
    }, headers=headers)
    assert resp.status_code == 200
    assert settings.session_cookie_name in resp.cookies


def test_verify_otp_issues_session_cookie(client):
    headers = {"X-Requested-With": "XMLHttpRequest"}
    client.post("/api/auth/register", json={
        "name": "Cara Scholar",
        "email": "cara@example.com",
        "password": "Password123",
        "confirm_password": "Password123"
    }, headers=headers)

    from user_auth.email_service import email_service
    sent = email_service.sent_emails[-1]
    import re
    otp_match = re.search(r"\b(\d{6})\b", sent["text"])
    assert otp_match
    otp = otp_match.group(1)

    v_resp = client.post("/api/auth/verify-otp", json={
        "email": "cara@example.com",
        "otp": otp
    }, headers=headers)
    assert v_resp.status_code == 200
    assert settings.session_cookie_name in v_resp.cookies
    cookie = v_resp.cookies[settings.session_cookie_name]
    assert len(cookie) > 20


def test_login_wrong_password_generic_error(client):
    headers = {"X-Requested-With": "XMLHttpRequest"}
    client.post("/api/auth/register", json={
        "name": "Bob Scholar",
        "email": "bob@example.com",
        "password": "Password123",
        "confirm_password": "Password123"
    }, headers=headers)

    resp = client.post("/api/auth/login", json={
        "email": "bob@example.com",
        "password": "WrongPassword123"
    }, headers=headers)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password"


def test_login_unknown_email_generic_error_and_timing_defense(client):
    headers = {"X-Requested-With": "XMLHttpRequest"}
    with patch("user_auth.service.verify_password", wraps=lambda p, h: False) as mock_verify:
        resp = client.post("/api/auth/login", json={
            "email": "nonexistent@example.com",
            "password": "RandomPassword123"
        }, headers=headers)
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid email or password"
        # Dummy hash comparison was executed (Condition 2 & 3)
        assert mock_verify.called


def test_login_deactivated_account_check_order(client, setup_in_memory_auth):
    """Account is deactivated (403) is revealed ONLY after a correct password (Condition 2)."""
    headers = {"X-Requested-With": "XMLHttpRequest"}
    client.post("/api/auth/register", json={
        "name": "Charlie",
        "email": "charlie@example.com",
        "password": "Password123",
        "confirm_password": "Password123"
    }, headers=headers)

    # Deactivate account directly in storage
    user = setup_in_memory_auth.get_user_by_email("charlie@example.com")
    setup_in_memory_auth.update_user(user["id"], {"is_active": False})

    # Wrong password -> still returns 401 (does NOT leak that account is deactivated)
    r1 = client.post("/api/auth/login", json={
        "email": "charlie@example.com",
        "password": "WrongPassword123"
    }, headers=headers)
    assert r1.status_code == 401
    assert r1.json()["detail"] == "Invalid email or password"

    # Correct password -> returns 403 Account is deactivated
    r2 = client.post("/api/auth/login", json={
        "email": "charlie@example.com",
        "password": "Password123"
    }, headers=headers)
    assert r2.status_code == 403
    assert r2.json()["detail"] == "Account is deactivated"


def test_demo_user_neutralization(client, setup_in_memory_auth):
    """Demo user user@platform.ai is neutralized and rejected with 401 (Condition 1)."""
    # Seed demo user in storage
    setup_in_memory_auth.create_user({
        "id": "00000000-0000-0000-0000-000000000001",
        "username": "user@platform.ai",
        "email": "user@platform.ai",
        "hashed_password": "pbkdf2_sha256$600000$salt$hash",
        "role": "user",
        "is_active": True
    })

    # When neutralized, login is hard-blocked
    headers = {"X-Requested-With": "XMLHttpRequest"}
    resp = client.post("/api/auth/login", json={
        "email": "user@platform.ai",
        "password": "user123"
    }, headers=headers)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email or password"

    # Admin login with 'user' and 'user@platform.ai' and password 'user123' returns 401 (Question 2)
    admin_resp1 = client.post("/api/admin/auth/login", json={
        "username": "user",
        "password": "user123"
    })
    assert admin_resp1.status_code == 401
    assert "Incorrect username or password" in admin_resp1.json()["detail"]

    admin_resp2 = client.post("/api/admin/auth/login", json={
        "username": "user@platform.ai",
        "password": "user123"
    })
    assert admin_resp2.status_code == 401
    assert "Incorrect username or password" in admin_resp2.json()["detail"]


def test_admin_login_with_demo_usernames_returns_401(client):
    """Admin login with neutralized demo accounts ('user' and 'user@platform.ai') returns 401."""
    resp1 = client.post("/api/admin/auth/login", json={
        "username": "user",
        "password": "user123"
    })
    assert resp1.status_code == 401
    assert "Incorrect username or password" in resp1.json()["detail"]

    resp2 = client.post("/api/admin/auth/login", json={
        "username": "user@platform.ai",
        "password": "user123"
    })
    assert resp2.status_code == 401
    assert "Incorrect username or password" in resp2.json()["detail"]


def test_lockout_after_repeated_failures(client):
    """5 consecutive failures for (email, IP) initiates lockout (Condition 10)."""
    headers = {"X-Requested-With": "XMLHttpRequest"}
    for i in range(5):
        resp = client.post("/api/auth/login", json={
            "email": "target@example.com",
            "password": f"WrongPass{i}"
        }, headers=headers)
        assert resp.status_code == 401

    # 6th attempt triggers 429 lockout
    locked_resp = client.post("/api/auth/login", json={
        "email": "target@example.com",
        "password": "AnyPassword"
    }, headers=headers)
    assert locked_resp.status_code == 429
    assert "Account temporarily locked" in locked_resp.json()["detail"]


# ---------------------------------------------------------------------------
# 4. Session Lifecycle, Logout, and Expiry (Condition 7 & 11)
# ---------------------------------------------------------------------------
def test_get_current_user_profile(client):
    headers = {"X-Requested-With": "XMLHttpRequest"}
    client.post("/api/auth/register", json={
        "name": "Dana Scholar",
        "email": "dana@example.com",
        "password": "Password123",
        "confirm_password": "Password123"
    }, headers=headers)

    from user_auth.email_service import email_service
    sent = email_service.sent_emails[-1]
    import re
    otp = re.search(r"\b(\d{6})\b", sent["text"]).group(1)
    v_resp = client.post("/api/auth/verify-otp", json={"email": "dana@example.com", "otp": otp}, headers=headers)
    cookie = v_resp.cookies[settings.session_cookie_name]

    # Call /api/auth/me with cookie
    me_resp = client.get("/api/auth/me", headers={"Cookie": f"{settings.session_cookie_name}={cookie}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "dana@example.com"
    assert me_resp.json()["full_name"] == "Dana Scholar"


def test_logout_revokes_session(client):
    headers = {"X-Requested-With": "XMLHttpRequest"}
    client.post("/api/auth/register", json={
        "name": "Dana Scholar",
        "email": "dana@example.com",
        "password": "Password123",
        "confirm_password": "Password123"
    }, headers=headers)

    from user_auth.email_service import email_service
    sent = email_service.sent_emails[-1]
    import re
    otp = re.search(r"\b(\d{6})\b", sent["text"]).group(1)
    v_resp = client.post("/api/auth/verify-otp", json={"email": "dana@example.com", "otp": otp}, headers=headers)
    cookie = v_resp.cookies[settings.session_cookie_name]

    # Logout
    logout_resp = client.post("/api/auth/logout", headers={
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": f"{settings.session_cookie_name}={cookie}"
    })
    assert logout_resp.status_code == 200

    # /api/auth/me with old cookie now fails with 401
    me_resp = client.get("/api/auth/me", headers={"Cookie": f"{settings.session_cookie_name}={cookie}"})
    assert me_resp.status_code == 401


# ---------------------------------------------------------------------------
# 5. Google OAuth Flow Tests (Condition 7 & 8)
# ---------------------------------------------------------------------------
def test_public_auth_config_endpoint(client):
    """GET /api/auth/config returns public google_client_id (Condition 8)."""
    settings.google_client_id = "test-client-id-12345.apps.googleusercontent.com"
    resp = client.get("/api/auth/config")
    assert resp.status_code == 200
    assert resp.json()["google_client_id"] == "test-client-id-12345.apps.googleusercontent.com"


def test_google_login_new_user(client):
    settings.google_client_id = "test-client-id"
    headers = {"X-Requested-With": "XMLHttpRequest"}

    fake_payload = {
        "sub": "google-sub-001",
        "email": "google.user@example.com",
        "email_verified": True,
        "name": "Google User",
    }
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_payload):
        resp = client.post("/api/auth/google", json={"credential": "fake-google-jwt-token"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "google.user@example.com"
        assert data["email_verified"] is True
        assert data["role"] == "user"
        assert settings.session_cookie_name in resp.cookies


def test_google_login_links_existing_and_revokes_sessions(client, setup_in_memory_auth):
    """Google login links to existing account, clears password, and revokes all old sessions (Condition 7)."""
    settings.google_client_id = "test-client-id"
    headers = {"X-Requested-With": "XMLHttpRequest"}

    # Register user with password (starts as unverified account)
    reg_resp = client.post("/api/auth/register", json={
        "name": "Eve PreReg",
        "email": "eve@example.com",
        "password": "Password123",
        "confirm_password": "Password123"
    }, headers=headers)
    assert reg_resp.status_code == 200
    user_id = reg_resp.json()["id"]

    # Issue an old active session to simulate pre-existing session
    from user_auth.security import hash_session_token
    raw_token = "old-session-token-eve"
    setup_in_memory_auth.create_session({
        "id": "old-sess-1",
        "user_id": user_id,
        "token_hash": hash_session_token(raw_token),
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
        "revoked_at": None,
    })
    old_cookie = raw_token

    # Verify old session works
    assert client.get("/api/auth/me", headers={"Cookie": f"{settings.session_cookie_name}={old_cookie}"}).status_code == 200

    # User signs in via Google with same verified email
    fake_payload = {
        "sub": "google-sub-eve-123",
        "email": "eve@example.com",
        "email_verified": True,
        "name": "Eve Google",
    }
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_payload):
        g_resp = client.post("/api/auth/google", json={"credential": "fake-google-jwt-token"}, headers=headers)
        assert g_resp.status_code == 200
        new_cookie = g_resp.cookies[settings.session_cookie_name]

    # Old session is revoked (Condition 7)
    old_me = client.get("/api/auth/me", headers={"Cookie": f"{settings.session_cookie_name}={old_cookie}"})
    assert old_me.status_code == 401

    # New session works
    new_me = client.get("/api/auth/me", headers={"Cookie": f"{settings.session_cookie_name}={new_cookie}"})
    assert new_me.status_code == 200

    # Password has been cleared to prevent pre-registration account takeover (Condition 7)
    user_row = setup_in_memory_auth.get_user_by_email("eve@example.com")
    assert user_row["hashed_password"] is None
    assert user_row["google_sub"] == "google-sub-eve-123"


def test_google_login_rejects_sub_mismatch(client, setup_in_memory_auth):
    """Reject Google login if existing account is already linked to a different google_sub (Condition 8)."""
    settings.google_client_id = "test-client-id"
    headers = {"X-Requested-With": "XMLHttpRequest"}

    # Create user already linked to sub-A
    setup_in_memory_auth.create_user({
        "id": "00000000-0000-0000-0000-000000000099",
        "username": "linked_user",
        "email": "linked@example.com",
        "google_sub": "google-sub-ORIGINAL",
        "email_verified": True,
        "role": "user",
        "is_active": True
    })

    # Attempt sign-in with different sub
    fake_payload = {
        "sub": "google-sub-DIFFERENT",
        "email": "linked@example.com",
        "email_verified": True,
        "name": "Hacker Impersonator",
    }
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_payload):
        resp = client.post("/api/auth/google", json={"credential": "fake-google-jwt-token"}, headers=headers)
        assert resp.status_code == 409
        assert "linked to a different Google account" in resp.json()["detail"]


def test_google_login_repeat_login(client, setup_in_memory_auth):
    """Repeat Google login for the same sub succeeds and updates last_login."""
    settings.google_client_id = "test-client-id"
    headers = {"X-Requested-With": "XMLHttpRequest"}

    fake_payload = {
        "sub": "google-sub-repeat-123",
        "email": "repeat.user@example.com",
        "email_verified": True,
        "name": "Repeat User",
    }
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_payload):
        # 1st login
        resp1 = client.post("/api/auth/google", json={"credential": "fake-google-jwt-token-1"}, headers=headers)
        assert resp1.status_code == 200
        cookie1 = resp1.cookies[settings.session_cookie_name]
        user1 = setup_in_memory_auth.get_user_by_google_sub("google-sub-repeat-123")
        assert user1 is not None

        # 2nd login (repeat)
        resp2 = client.post("/api/auth/google", json={"credential": "fake-google-jwt-token-2"}, headers=headers)
        assert resp2.status_code == 200
        cookie2 = resp2.cookies[settings.session_cookie_name]
        user2 = setup_in_memory_auth.get_user_by_google_sub("google-sub-repeat-123")
        assert user2["id"] == user1["id"]
        assert user2.get("last_login") is not None
        assert cookie2 != cookie1


def test_google_login_wrong_audience(client):
    """Google login rejects token with wrong audience with 401."""
    settings.google_client_id = "test-client-id"
    headers = {"X-Requested-With": "XMLHttpRequest"}

    with patch("google.oauth2.id_token.verify_oauth2_token", side_effect=ValueError("Token has wrong audience")):
        resp = client.post("/api/auth/google", json={"credential": "wrong-audience-token"}, headers=headers)
        assert resp.status_code == 401
        assert "Google token verification failed" in resp.json()["detail"]


def test_google_login_expired_token(client):
    """Google login rejects expired token with 401."""
    settings.google_client_id = "test-client-id"
    headers = {"X-Requested-With": "XMLHttpRequest"}

    with patch("google.oauth2.id_token.verify_oauth2_token", side_effect=ValueError("Token has expired")):
        resp = client.post("/api/auth/google", json={"credential": "expired-token"}, headers=headers)
        assert resp.status_code == 401
        assert "Google token verification failed" in resp.json()["detail"]


def test_google_login_unverified_email(client):
    """Google login rejects unverified email with 400."""
    settings.google_client_id = "test-client-id"
    headers = {"X-Requested-With": "XMLHttpRequest"}

    fake_payload = {
        "sub": "google-sub-unverified",
        "email": "unverified@example.com",
        "email_verified": False,
        "name": "Unverified User",
    }
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_payload):
        resp = client.post("/api/auth/google", json={"credential": "unverified-token"}, headers=headers)
        assert resp.status_code == 400
        assert "Google email is not verified" in resp.json()["detail"]


def test_google_login_with_admin_email_creates_regular_user_only(client, setup_in_memory_auth):
    """Google login with an email matching an admin creates a regular user in app_users only, never admin tables."""
    settings.google_client_id = "test-client-id"
    headers = {"X-Requested-With": "XMLHttpRequest"}

    from admin_backend.routes import auth_routes
    initial_admin_count = len(auth_routes.user_storage._users_by_id)

    fake_payload = {
        "sub": "google-sub-admin-email",
        "email": "admin@platform.ai",
        "email_verified": True,
        "name": "Admin Impersonator",
    }
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_payload):
        resp = client.post("/api/auth/google", json={"credential": "fake-google-token"}, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["role"] == "user"
        assert data["email"] == "admin@platform.ai"
        cookie = resp.cookies[settings.session_cookie_name]

    # Verify regular user exists in app_users
    regular_user = setup_in_memory_auth.get_user_by_email("admin@platform.ai")
    assert regular_user is not None
    assert regular_user["role"] == "user"
    assert regular_user["google_sub"] == "google-sub-admin-email"

    # Verify admin table is completely untouched
    assert len(auth_routes.user_storage._users_by_id) == initial_admin_count
    admin_row = auth_routes.user_storage.get_by_username("admin")
    assert "google_sub" not in admin_row or admin_row.get("google_sub") != "google-sub-admin-email"

    # Verify regular user cookie cannot access guarded admin routes
    admin_probe = client.get("/admin/metrics/summary", headers={"Cookie": f"{settings.session_cookie_name}={cookie}"})
    assert admin_probe.status_code in (401, 403)


# ---------------------------------------------------------------------------
# 6. Admin and Regular User Structural Isolation Tests (Condition 5 & 7)
# ---------------------------------------------------------------------------
def test_admin_login_with_google_only_user_returns_clean_401(client, setup_in_memory_auth):
    """Admin login with a Google-only user's username returns clean 401, not 500 (Condition 5 & 7)."""
    # Create Google user with NULL password in both user auth and admin user storage
    from admin_backend.routes import auth_routes
    google_user_dict = {
        "id": "00000000-0000-0000-0000-000000000088",
        "username": "google.only.user",
        "email": "google.only@example.com",
        "hashed_password": None,
        "role": "user",
        "google_sub": "sub-12345",
        "email_verified": True,
        "is_active": True
    }
    setup_in_memory_auth.create_user(google_user_dict)
    auth_routes.user_storage.create_user(google_user_dict)

    # Call admin login endpoint with this username
    resp = client.post("/api/admin/auth/login", json={
        "username": "google.only.user",
        "password": "AnyRandomPassword123!"
    })
    assert resp.status_code == 401
    assert "Incorrect username or password" in resp.json()["detail"]


def test_user_role_jwt_cannot_access_admin_routes(client):
    """User-role JWT is blocked with 403 on EVERY admin route that enforces require_admin_role (Condition 7 and Question 4)."""
    from admin_backend.security.tokens import create_access_token
    user_token = create_access_token(user_id="user-123", username="testuser", role="user")
    headers = {"Authorization": f"Bearer {user_token}"}

    guarded_admin_endpoints = [
        ("GET", "/admin/health"),
        ("GET", "/admin/metrics/summary"),
        ("GET", "/admin/metrics/latency"),
        ("GET", "/admin/quality/scores"),
        ("GET", "/admin/quality/summary"),
        ("POST", "/admin/quality/human-reviews"),
        ("GET", "/admin/quality/human-reviews"),
        ("GET", "/admin/traces"),
        ("GET", "/admin/traces/00000000-0000-0000-0000-000000000001"),
        ("GET", "/admin/safety/events"),
        ("GET", "/admin/safety/redteam"),
        ("GET", "/admin/memory/reports"),
        ("DELETE", "/admin/memory/reports/00000000-0000-0000-0000-000000000001?confirm=true"),
        ("GET", "/admin/memory/cache"),
        ("DELETE", "/admin/memory/cache/test_entry?confirm=true"),
        ("POST", "/admin/memory/cache/clear?confirm=true"),
        ("GET", "/admin/memory/sessions"),
        ("GET", "/admin/config/draft"),
        ("GET", "/admin/export/scores/csv"),
        ("GET", "/admin/export/scores/json"),
        ("GET", "/admin/audit/logs"),
        ("GET", "/admin/audit/user-activity"),
    ]

    for method, path in guarded_admin_endpoints:
        if method == "GET":
            resp = client.get(path, headers=headers)
        elif method == "POST":
            resp = client.post(path, headers=headers, json={})
        elif method == "DELETE":
            resp = client.delete(path, headers=headers)
        assert resp.status_code == 403, f"Expected 403 on {method} {path}, got {resp.status_code}: {resp.text}"
        assert "Admin privileges required" in resp.json()["detail"]

    # Verify GET /admin/auth/me (guarded by get_current_user only) allows the user-role JWT
    me_resp = client.get("/admin/auth/me", headers=headers)
    assert me_resp.status_code == 200
    assert me_resp.json()["role"] == "user" 


def test_registering_with_admin_email_does_not_affect_admin_account(client):
    """Registering with an admin's email in user_auth creates app_users row without touching admin_users (Condition 7)."""
    headers = {"X-Requested-With": "XMLHttpRequest"}
    # Register regular user using admin@platform.ai
    resp = client.post("/api/auth/register", json={
        "name": "Regular Person",
        "email": "admin@platform.ai",
        "password": "UserPassword123",
        "confirm_password": "UserPassword123"
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["role"] == "user"

    # Admin login still works with admin credentials
    admin_login_resp = client.post("/api/admin/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    assert admin_login_resp.status_code == 200
    assert admin_login_resp.json()["role"] == "admin"


# ---------------------------------------------------------------------------
# 7. Fail-Fast 503 and REQUIRE_LOGIN in /generate (Condition 9 & 13)
# ---------------------------------------------------------------------------
def test_generate_works_for_unauthenticated_guests_when_require_login_false(client):
    """Guests can generate reports when REQUIRE_LOGIN=false (default)."""
    settings.require_login = False
    with patch("api.main.parts.run_pipeline", return_value={"report": "Guest research report."}), \
         patch("api.main.parts.check_cache", return_value=None), \
         patch("api.main.parts.get_history", return_value=[]), \
         patch("api.main.parts.save_to_ltm", return_value=None), \
         patch("api.main._remember", return_value=None), \
         patch("api.main.check_input", return_value=(True, "ok")), \
         patch("api.main.check_output", return_value=(True, "ok")), \
         patch("api.main.grade_report", return_value=None):
        resp = client.post("/generate", json={"topic": "Quantum computing advances", "grade": False})
        assert resp.status_code == 200
        assert resp.json()["report"] == "Guest research report."


def test_generate_requires_auth_when_require_login_true(client):
    """Guests get 401 when REQUIRE_LOGIN=true."""
    settings.require_login = True
    resp = client.post("/generate", json={"topic": "Quantum computing advances"})
    assert resp.status_code == 401
    assert "Authentication required" in resp.json()["detail"]


def test_generate_returns_503_when_require_login_true_and_storage_is_down(client, setup_in_memory_auth):
    """When REQUIRE_LOGIN=true and database is down, return 503, not 401 (Condition 9 & 13)."""
    settings.require_login = True
    setup_in_memory_auth.simulate_db_down = True
    resp = client.post("/generate", json={"topic": "Quantum computing advances"})
    assert resp.status_code == 503
    assert "temporarily unavailable" in resp.json()["detail"]


def test_query_audit_entries_handles_uuid_id():
    """Verify that PostgresAuditStorage.query_audit_entries converts UUID to str without raising validation error."""
    import uuid
    from datetime import datetime, timezone
    from unittest.mock import MagicMock
    from admin_backend.storage.postgres import PostgresAuditStorage
    from admin_backend.models.audit import AuditLogFilter

    storage = PostgresAuditStorage("postgresql://test:test@localhost:5432/test")
    fake_uuid = uuid.uuid4()
    fake_row = {
        "id": fake_uuid,
        "timestamp": datetime.now(timezone.utc),
        "actor_username": "admin",
        "actor_role": "admin",
        "action": "auth.login",
        "resource_type": "auth",
        "resource_id": "1",
        "status": "success",
        "details": {"method": "password"},
        "client_ip": "127.0.0.1",
    }

    mock_conn = MagicMock()
    mock_conn.execute.return_value.fetchall.return_value = [fake_row]
    storage._connect = MagicMock()
    storage._connect.return_value.__enter__.return_value = mock_conn

    entries = storage.query_audit_entries(AuditLogFilter())
    assert len(entries) == 1
    assert entries[0].id == str(fake_uuid)
    assert isinstance(entries[0].id, str)

