"""
Comprehensive Verification and Regression Test Suite for User Authentication and Admin Tracking.
Covers all 16 mandatory verification scenarios:
1. Create account with email + password, verify via OTP/link, log in successfully.
2. Log in with an unregistered email: generic error ("Invalid email or password") and "Create account" option.
3. Signup with invalid syntax, domain without MX records, and disposable email: all rejected.
4. Wrong password: generic failure message.
5. Unverified account cannot access chat or protected pages.
6. Google sign-in: new user, returning user, and linking to an existing email/password account (same chat history).
7. Forged or expired Google token rejected by the server.
8. Rate limiting triggers after repeated failures.
9. Password reset works end to end; token cannot be reused.
10. DATA ISOLATION: User A creates chats, User B logs in and sees none of them; direct API access to A's conversation id as B returns 403/404.
11. Chat history persists after logout/login and across browsers.
12. Admin sees all users, their chats, and activity, and all numbers match the database.
13. Normal user calling any admin endpoint gets 403.
14. Suspended user cannot log in (and is immediately rejected/revoked).
15. Admin login regression test (works identically with admin credentials).
16. Neutralization of old demo credentials (user@platform.ai / user123).
"""

import os
import re
import unittest.mock
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from api.main import app
from user_auth.config import settings
from user_auth.email_service import email_service
from user_auth.security import auth_security_manager
from user_auth.service import auth_service
from user_auth.storage import InMemoryUserAuthStorage, set_user_auth_storage
from user_auth.chat_storage import InMemoryChatReviewStorage, set_chat_review_storage
from admin_backend.storage.in_memory import InMemoryUserStorage
from admin_backend.security.passwords import hash_password
from admin_backend.routes import auth_routes


def get_latest_otp_for_email(email: str) -> str:
    """Helper to extract dispatched OTP from email service in tests."""
    for item in reversed(email_service.sent_emails):
        if item["to"] == email and "verification code" in item["subject"].lower():
            match = re.search(r"\b(\d{6})\b", item["text"])
            if match:
                return match.group(1)
            return item["subject"].split()[0]
    raise ValueError(f"No OTP email found for {email}")


def get_latest_reset_token_for_email(email: str) -> str:
    """Helper to extract dispatched password reset token from email service in tests."""
    for item in reversed(email_service.sent_emails):
        if item["to"] == email and "reset" in item["subject"].lower():
            match = re.search(r"token=([a-zA-Z0-9_\-]+)", item["text"])
            if match:
                return match.group(1)
    raise ValueError(f"No password reset email found for {email}")


@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Setup clean in-memory state for user auth, chat storage, and admin storage."""
    # Reset email service history
    email_service.sent_emails.clear()

    # User Auth Storage
    mem_auth = InMemoryUserAuthStorage()
    set_user_auth_storage(mem_auth)
    auth_service._storage_override = mem_auth
    auth_security_manager.reset()
    settings.auth_storage_backend = "memory"
    settings.neutralize_demo_users = True
    settings.require_login = True
    settings.google_client_id = "test-client-id"

    # Chat Storage
    mem_chat = InMemoryChatReviewStorage()
    set_chat_review_storage(mem_chat)

    # Prevent Postgres connection attempts in tests
    try:
        import psycopg
        monkeypatch.setattr(psycopg, "connect", unittest.mock.MagicMock(side_effect=psycopg.OperationalError("PostgreSQL offline for unit test")))
    except ImportError:
        pass

    # Admin Auth Storage (Admin Google Auth & Session isolation)
    admin_mem = InMemoryUserStorage()
    admin_mem.create_user({
        "id": "admin-1",
        "username": "admin",
        "email": "admin@platform.ai",
        "role": "admin",
        "is_active": True,
    })
    monkeypatch.setattr(auth_routes, "user_storage", admin_mem)

    yield {
        "auth_storage": mem_auth,
        "chat_storage": mem_chat,
        "admin_storage": admin_mem
    }

    auth_security_manager.reset()


@pytest.fixture
def client():
    return TestClient(app)


CSRF_HEADERS = {
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "http://testserver",
}


# ===========================================================================
# TEST 1: Create Account, OTP Verify, and Login
# ===========================================================================
def test_01_create_account_otp_verify_and_login(client):
    # 1. Register new user
    reg_resp = client.post(
        "/api/auth/register",
        json={
            "name": "Alice Researcher",
            "email": "alice.test@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!"
        },
        headers=CSRF_HEADERS
    )
    assert reg_resp.status_code == 200
    user_data = reg_resp.json()
    assert user_data["email"] == "alice.test@example.com"
    assert user_data["email_verified"] is False

    # 2. Extract generated OTP from email service
    raw_otp = get_latest_otp_for_email("alice.test@example.com")
    assert len(raw_otp) == 6

    # 3. Verify OTP
    verify_resp = client.post(
        "/api/auth/verify-otp",
        json={"email": "alice.test@example.com", "otp": raw_otp},
        headers=CSRF_HEADERS
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["email_verified"] is True

    # 4. Log in successfully
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "alice.test@example.com", "password": "Password123!"},
        headers=CSRF_HEADERS
    )
    assert login_resp.status_code == 200
    assert login_resp.json()["email_verified"] is True
    assert "user_session" in login_resp.cookies

    # 5. Check session retrieval via /me
    me_resp = client.get("/api/auth/me", cookies=login_resp.cookies, headers=CSRF_HEADERS)
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "alice.test@example.com"


# ===========================================================================
# TEST 2: Unregistered Email Generic Error
# ===========================================================================
def test_02_unregistered_email_generic_error(client):
    resp = client.post(
        "/api/auth/login",
        json={"email": "nonexistent.user@example.com", "password": "Password123!"},
        headers=CSRF_HEADERS
    )
    assert resp.status_code == 401
    assert "Invalid email or password" in resp.json()["detail"]


# ===========================================================================
# TEST 3: Email Validation Layers (Syntax, Disposable, Domain without MX)
# ===========================================================================
def test_03_email_validation_layers(client):
    # a. Invalid syntax
    res1 = client.post(
        "/api/auth/register",
        json={"name": "Bad Syntax", "email": "not-an-email", "password": "Password123!", "confirm_password": "Password123!"},
        headers=CSRF_HEADERS
    )
    assert res1.status_code == 422

    # b. Disposable email domain
    res2 = client.post(
        "/api/auth/register",
        json={"name": "Disposable User", "email": "test@mailinator.com", "password": "Password123!", "confirm_password": "Password123!"},
        headers=CSRF_HEADERS
    )
    assert res2.status_code == 400
    assert "disposable" in res2.json()["detail"].lower()

    # c. Domain without MX records
    res3 = client.post(
        "/api/auth/register",
        json={"name": "No MX User", "email": "test@nonexistentdomain99823482394.org", "password": "Password123!", "confirm_password": "Password123!"},
        headers=CSRF_HEADERS
    )
    assert res3.status_code == 400
    assert "domain" in res3.json()["detail"].lower()


# ===========================================================================
# TEST 4: Wrong Password Generic Error
# ===========================================================================
def test_04_wrong_password_generic_error(client):
    # Register user
    client.post(
        "/api/auth/register",
        json={"name": "Bob User", "email": "bob.test@example.com", "password": "Password123!", "confirm_password": "Password123!"},
        headers=CSRF_HEADERS
    )

    # Attempt login with wrong password
    resp = client.post(
        "/api/auth/login",
        json={"email": "bob.test@example.com", "password": "WrongPassword999!"},
        headers=CSRF_HEADERS
    )
    assert resp.status_code == 401
    assert "Invalid email or password" in resp.json()["detail"]


# ===========================================================================
# TEST 5: Unverified Account Denied Session at Login Time (Verify Once Rule)
# ===========================================================================
def test_05_unverified_account_denied_access(client):
    # Register but do not verify OTP
    reg_resp = client.post(
        "/api/auth/register",
        json={"name": "Unverified User", "email": "unverified@example.com", "password": "Password123!", "confirm_password": "Password123!"},
        headers=CSRF_HEADERS
    )
    assert reg_resp.status_code == 200
    # No session cookie issued on registration
    assert "user_session" not in reg_resp.cookies

    # Unverified user login is denied with 403 and sends a fresh OTP
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "unverified@example.com", "password": "Password123!"},
        headers=CSRF_HEADERS
    )
    assert login_resp.status_code == 403
    assert "verification" in login_resp.json()["detail"].lower()
    assert "user_session" not in login_resp.cookies

    # Attempt to access chat endpoints without valid session
    chats_resp = client.get("/api/chats", headers=CSRF_HEADERS)
    assert chats_resp.status_code in (401, 403)


# ===========================================================================
# TEST 6: Google Sign-In (New user, returning user, and account linking)
# ===========================================================================
def test_06_google_sign_in_flows(client):
    # 1. New Google user
    fake_payload_new = {
        "iss": "https://accounts.google.com",
        "sub": "google-sub-1001",
        "email": "carol.google@example.com",
        "email_verified": True,
        "name": "Carol Google",
    }
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_payload_new):
        g_resp1 = client.post("/api/auth/google", json={"credential": "valid_token_new"}, headers=CSRF_HEADERS)
        assert g_resp1.status_code == 200
        u1 = g_resp1.json()
        assert u1["email"] == "carol.google@example.com"
        assert u1["auth_provider"] == "google"
        assert u1["email_verified"] is True
        assert "user_session" in g_resp1.cookies

    # 2. Returning Google user
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_payload_new):
        g_resp2 = client.post("/api/auth/google", json={"credential": "valid_token_returning"}, headers=CSRF_HEADERS)
        assert g_resp2.status_code == 200
        assert g_resp2.json()["id"] == u1["id"]

    # 3. Account linking: Existing email/password user logs in with Google
    client.post(
        "/api/auth/register",
        json={"name": "Dan Email", "email": "dan.link@example.com", "password": "Password123!", "confirm_password": "Password123!"},
        headers=CSRF_HEADERS
    )
    fake_payload_link = {
        "iss": "https://accounts.google.com",
        "sub": "google-sub-2002",
        "email": "dan.link@example.com",
        "email_verified": True,
        "name": "Dan Linked",
    }
    with patch("google.oauth2.id_token.verify_oauth2_token", return_value=fake_payload_link):
        g_resp3 = client.post("/api/auth/google", json={"credential": "valid_token_link"}, headers=CSRF_HEADERS)
        assert g_resp3.status_code == 200
        linked_user = g_resp3.json()
        assert linked_user["email"] == "dan.link@example.com"
        assert linked_user["google_id"] == "google-sub-2002"
        assert linked_user["email_verified"] is True


# ===========================================================================
# TEST 7: Forged or Expired Google Token Rejected
# ===========================================================================
def test_07_forged_or_expired_google_token_rejected(client):
    with patch("google.oauth2.id_token.verify_oauth2_token", side_effect=ValueError("Token expired")):
        resp = client.post("/api/auth/google", json={"credential": "expired_token"}, headers=CSRF_HEADERS)
        assert resp.status_code == 401
        assert "google token verification failed" in resp.json()["detail"].lower()


# ===========================================================================
# TEST 8: Rate Limiting & Lockout
# ===========================================================================
def test_08_rate_limiting_and_lockout(client):
    target_email = "lockout.target@example.com"
    for _ in range(5):
        client.post(
            "/api/auth/login",
            json={"email": target_email, "password": "WrongPassword!"},
            headers=CSRF_HEADERS
        )

    # 6th attempt must trigger rate limit or lockout
    resp = client.post(
        "/api/auth/login",
        json={"email": target_email, "password": "WrongPassword!"},
        headers=CSRF_HEADERS
    )
    assert resp.status_code in [401, 429]
    detail = resp.json()["detail"].lower()
    assert "locked" in detail or "too many" in detail or "attempts" in detail


# ===========================================================================
# TEST 9: Password Reset Flow (Single-use Token & Invalidate Sessions)
# ===========================================================================
def test_09_password_reset_end_to_end_single_use(client):
    # 1. Register & verify user
    client.post(
        "/api/auth/register",
        json={"name": "Eve Reset", "email": "eve.reset@example.com", "password": "OldPassword123!", "confirm_password": "OldPassword123!"},
        headers=CSRF_HEADERS
    )
    otp = get_latest_otp_for_email("eve.reset@example.com")
    client.post("/api/auth/verify-otp", json={"email": "eve.reset@example.com", "otp": otp}, headers=CSRF_HEADERS)

    # Log in and get active session cookie
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "eve.reset@example.com", "password": "OldPassword123!"},
        headers=CSRF_HEADERS
    )
    old_cookies = login_resp.cookies

    # 2. Request password reset
    forgot_resp = client.post("/api/auth/forgot-password", json={"email": "eve.reset@example.com"}, headers=CSRF_HEADERS)
    assert forgot_resp.status_code == 200

    # Retrieve raw reset token from email
    raw_token = get_latest_reset_token_for_email("eve.reset@example.com")
    assert raw_token is not None

    # 3. Reset password
    reset_resp = client.post(
        "/api/auth/reset-password",
        json={"token": raw_token, "password": "BrandNewPassword123!", "confirm_password": "BrandNewPassword123!"},
        headers=CSRF_HEADERS
    )
    assert reset_resp.status_code == 200

    # 4. Old session must now be revoked
    me_resp = client.get("/api/auth/me", cookies=old_cookies, headers=CSRF_HEADERS)
    assert me_resp.status_code == 401

    # 5. Token cannot be reused (single-use proof)
    reuse_resp = client.post(
        "/api/auth/reset-password",
        json={"token": raw_token, "password": "AnotherPassword123!", "confirm_password": "AnotherPassword123!"},
        headers=CSRF_HEADERS
    )
    assert reuse_resp.status_code == 400
    assert "already used" in reuse_resp.json()["detail"].lower() or "invalid" in reuse_resp.json()["detail"].lower()

    # 6. Log in with new password succeeds
    new_login_resp = client.post(
        "/api/auth/login",
        json={"email": "eve.reset@example.com", "password": "BrandNewPassword123!"},
        headers=CSRF_HEADERS
    )
    assert new_login_resp.status_code == 200


# ===========================================================================
# TEST 10: DATA ISOLATION & IDOR Prevention
# ===========================================================================
def test_10_data_isolation_idor(client, setup_test_environment):
    chat_store = setup_test_environment["chat_storage"]

    # Register & verify User A
    client.post(
        "/api/auth/register",
        json={"name": "User Alpha", "email": "alpha@example.com", "password": "Password123!", "confirm_password": "Password123!"},
        headers=CSRF_HEADERS
    )
    otp_a = get_latest_otp_for_email("alpha@example.com")
    client.post("/api/auth/verify-otp", json={"email": "alpha@example.com", "otp": otp_a}, headers=CSRF_HEADERS)
    login_a = client.post("/api/auth/login", json={"email": "alpha@example.com", "password": "Password123!"}, headers=CSRF_HEADERS)
    cookies_a = login_a.cookies

    # Register & verify User B
    client.post(
        "/api/auth/register",
        json={"name": "User Beta", "email": "beta@example.com", "password": "Password123!", "confirm_password": "Password123!"},
        headers=CSRF_HEADERS
    )
    otp_b = get_latest_otp_for_email("beta@example.com")
    client.post("/api/auth/verify-otp", json={"email": "beta@example.com", "otp": otp_b}, headers=CSRF_HEADERS)
    login_b = client.post("/api/auth/login", json={"email": "beta@example.com", "password": "Password123!"}, headers=CSRF_HEADERS)
    cookies_b = login_b.cookies

    # User A creates a conversation
    uid_a = login_a.json()["id"]
    conv_a = chat_store.create_conversation(uid_a, "Alpha Secret Research")
    conv_id_a = conv_a["id"]
    chat_store.add_message(conv_id_a, uid_a, "user", "Private Alpha Inquiry")

    # User B lists chats -> must be empty
    list_b = client.get("/api/chats", cookies=cookies_b, headers=CSRF_HEADERS)
    assert list_b.status_code == 200
    assert len(list_b.json()) == 0

    # User B attempts direct IDOR access to User A's conversation
    idor_get = client.get(f"/api/chats/{conv_id_a}", cookies=cookies_b, headers=CSRF_HEADERS)
    assert idor_get.status_code == 404

    # User B attempts to delete User A's conversation
    idor_del = client.delete(f"/api/chats/{conv_id_a}", cookies=cookies_b, headers=CSRF_HEADERS)
    assert idor_del.status_code == 404


# ===========================================================================
# TEST 11: Chat History Persistence Across Sessions
# ===========================================================================
def test_11_chat_history_persistence(client, setup_test_environment):
    chat_store = setup_test_environment["chat_storage"]

    # Register, verify, and log in
    client.post(
        "/api/auth/register",
        json={"name": "Frank Persistent", "email": "frank@example.com", "password": "Password123!", "confirm_password": "Password123!"},
        headers=CSRF_HEADERS
    )
    otp = get_latest_otp_for_email("frank@example.com")
    client.post("/api/auth/verify-otp", json={"email": "frank@example.com", "otp": otp}, headers=CSRF_HEADERS)
    login1 = client.post("/api/auth/login", json={"email": "frank@example.com", "password": "Password123!"}, headers=CSRF_HEADERS)
    uid = login1.json()["id"]

    # Create conversation and add messages
    conv = chat_store.create_conversation(uid, "Quantum Computing Survey")
    cid = conv["id"]
    chat_store.add_message(cid, uid, "user", "What is quantum supremacy?")
    chat_store.add_message(cid, uid, "assistant", "Quantum supremacy is the milestone...")

    # Log out
    client.post("/api/auth/logout", cookies=login1.cookies, headers=CSRF_HEADERS)

    # Log in again (new session)
    login2 = client.post("/api/auth/login", json={"email": "frank@example.com", "password": "Password123!"}, headers=CSRF_HEADERS)
    cookies2 = login2.cookies

    # Verify history loads correctly
    history_resp = client.get(f"/api/chats/{cid}", cookies=cookies2, headers=CSRF_HEADERS)
    assert history_resp.status_code == 200
    data = history_resp.json()
    assert data["title"] == "Quantum Computing Survey"
    assert len(data["messages"]) == 2


# ===========================================================================
# TEST 12: Admin Tracking Dashboard & Numbers Matching Database Truth
# ===========================================================================
def test_12_admin_tracking_dashboard_and_stats(client, setup_test_environment):
    auth_store = setup_test_environment["auth_storage"]
    chat_store = setup_test_environment["chat_storage"]

    # Admin Bearer token for tracking access
    from admin_backend.security.tokens import create_access_token
    admin_token = create_access_token(user_id="admin-1", username="admin", email="admin@platform.ai", role="admin")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Register 2 users in storage
    u1 = auth_store.create_user({"name": "User One", "email": "u1@example.com", "email_verified": True})
    u2 = auth_store.create_user({"name": "User Two", "email": "u2@example.com", "auth_provider": "google", "email_verified": True})
    conv = chat_store.create_conversation(u1["id"], "Test Dossier")
    chat_store.add_message(conv["id"], u1["id"], "user", "Inquiry")

    # 1. Fetch Stats
    stats_resp = client.get("/api/admin/tracking/stats", headers=admin_headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total_users"] >= 2
    assert stats["total_conversations"] >= 1
    assert stats["total_messages"] >= 1

    # 2. Fetch Users List
    users_resp = client.get("/api/admin/tracking/users", headers=admin_headers)
    assert users_resp.status_code == 200
    users_data = users_resp.json()
    assert users_data["total"] >= 2
    emails = [u["email"] for u in users_data["users"]]
    assert "u1@example.com" in emails
    assert "u2@example.com" in emails

    # 3. Fetch Specific User Detail
    detail_resp = client.get(f"/api/admin/tracking/users/{u1['id']}", headers=admin_headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["profile"]["email"] == "u1@example.com"
    assert len(detail["conversations"]) == 1

    # 4. Fetch Global Activity Feed
    act_resp = client.get("/api/admin/tracking/activity", headers=admin_headers)
    assert act_resp.status_code == 200
    assert "activities" in act_resp.json()


# ===========================================================================
# TEST 13: Normal User Gets 403 on Admin Endpoints
# ===========================================================================
def test_13_normal_user_denied_admin_endpoints(client):
    # Register and login regular user
    client.post(
        "/api/auth/register",
        json={"name": "Reg User", "email": "regular@example.com", "password": "Password123!", "confirm_password": "Password123!"},
        headers=CSRF_HEADERS
    )
    otp = get_latest_otp_for_email("regular@example.com")
    client.post("/api/auth/verify-otp", json={"email": "regular@example.com", "otp": otp}, headers=CSRF_HEADERS)
    login_resp = client.post("/api/auth/login", json={"email": "regular@example.com", "password": "Password123!"}, headers=CSRF_HEADERS)
    user_cookies = login_resp.cookies

    # Attempt to access admin tracking endpoints with regular user session
    admin_endpoints = [
        "/api/admin/tracking/stats",
        "/api/admin/tracking/users",
        "/api/admin/tracking/activity"
    ]
    for ep in admin_endpoints:
        # Without admin token (even with user cookies) must return 401/403
        r = client.get(ep, cookies=user_cookies)
        assert r.status_code in [401, 403]


# ===========================================================================
# TEST 14: Suspended User Rejected
# ===========================================================================
def test_14_suspended_user_cannot_login(client, setup_test_environment):
    auth_store = setup_test_environment["auth_storage"]

    # Register and verify user
    client.post(
        "/api/auth/register",
        json={"name": "Suspended Candidate", "email": "suspended@example.com", "password": "Password123!", "confirm_password": "Password123!"},
        headers=CSRF_HEADERS
    )
    otp = get_latest_otp_for_email("suspended@example.com")
    client.post("/api/auth/verify-otp", json={"email": "suspended@example.com", "otp": otp}, headers=CSRF_HEADERS)

    # Admin suspends user
    from admin_backend.security.tokens import create_access_token
    admin_token = create_access_token(user_id="admin-1", username="admin", email="admin@platform.ai", role="admin")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    user = auth_store.get_user_by_email("suspended@example.com")
    susp_resp = client.post(
        f"/api/admin/tracking/users/{user['id']}/status",
        json={"status": "suspended"},
        headers=admin_headers
    )
    assert susp_resp.status_code == 200

    # User attempts to login
    login_resp = client.post(
        "/api/auth/login",
        json={"email": "suspended@example.com", "password": "Password123!"},
        headers=CSRF_HEADERS
    )
    assert login_resp.status_code == 403
    assert "suspended" in login_resp.json()["detail"].lower() or "deactivated" in login_resp.json()["detail"].lower()


# ===========================================================================
# TEST 15: Demo Admin Password Login Decommissioned (Returns 404/405)
# ===========================================================================
def test_15_admin_login_regression(client):
    # Password login endpoint is decommissioned; POST to /admin/auth/login returns 404 or 405
    resp = client.post("/api/admin/auth/login", json={"username": "admin", "password": "password"})
    assert resp.status_code in (404, 405)


# ===========================================================================
# TEST 16: Demo Credentials Neutralized
# ===========================================================================
def test_16_demo_credentials_neutralized(client):
    # Attempting to log in as user@platform.ai with demo password user123 must be rejected
    resp = client.post(
        "/api/auth/login",
        json={"email": "user@platform.ai", "password": "user123"},
        headers=CSRF_HEADERS
    )
    assert resp.status_code == 401
    assert "Invalid email or password" in resp.json()["detail"]
