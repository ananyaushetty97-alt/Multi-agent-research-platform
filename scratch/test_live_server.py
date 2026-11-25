import os
import sys
sys.path.insert(0, os.path.abspath("."))
import requests

BASE_URL = "http://localhost:8000"

print("--- 1. Testing Unauthenticated Access to Admin Endpoints ---")
admin_endpoints = [
    "/api/admin/metrics/summary",
    "/api/admin/audit/logs",
    "/api/admin/tracking/stats",
    "/admin/auth/me",
]
for ep in admin_endpoints:
    r = requests.get(f"{BASE_URL}{ep}")
    print(f"GET {ep} -> Status: {r.status_code}")
    assert r.status_code == 401, f"Expected 401 for {ep}, got {r.status_code}"

print("\n--- 2. Testing Unauthenticated Access to User Endpoints ---")
user_endpoints = [
    "/api/auth/me",
    "/api/chats"
]
for ep in user_endpoints:
    r = requests.get(f"{BASE_URL}{ep}")
    print(f"GET {ep} -> Status: {r.status_code}")
    assert r.status_code == 401, f"Expected 401 for {ep}, got {r.status_code}"

print("\n--- 3. Testing Static HTML Protection ---")
r_admin = requests.get(f"{BASE_URL}/admin/index.html")
print(f"GET /admin/index.html -> Status: {r_admin.status_code}")
assert "admin-auth-gate" in r_admin.text, "admin-auth-gate must be in admin/index.html"
assert 'id="app-root"' in r_admin.text and 'style="display: none;"' in r_admin.text, "app-root must have display: none"
print("PASS: Admin index.html delivers with #app-root hidden and #admin-auth-gate present.")

r_user = requests.get(f"{BASE_URL}/user/index.html")
print(f"GET /user/index.html -> Status: {r_user.status_code}")
assert "login-modal" in r_user.text, "login-modal must be present in user/index.html"
print("PASS: User index.html delivers correctly.")

print("\n--- 4. Testing Role Isolation with Normal User Token on Admin API ---")
from admin_backend.security.tokens import create_access_token
# User role token
user_token = create_access_token(user_id="user-123", username="normal_user", email="reviewer_2a92f2@example.com", role="user")
headers = {"Authorization": f"Bearer {user_token}"}
r_admin_forbidden = requests.get(f"{BASE_URL}/api/admin/metrics/summary", headers=headers)
print(f"GET /api/admin/metrics/summary with User token -> Status: {r_admin_forbidden.status_code}")
assert r_admin_forbidden.status_code == 403, f"Expected 403 Forbidden, got {r_admin_forbidden.status_code}"

# Admin role token for comparison
admin_token = create_access_token(user_id="admin-123", username="admin_user", email="devaraddi31@gmail.com", role="admin")
headers_admin = {"Authorization": f"Bearer {admin_token}"}
r_admin_allowed = requests.get(f"{BASE_URL}/api/admin/metrics/summary", headers=headers_admin)
print(f"GET /api/admin/metrics/summary with Admin token -> Status: {r_admin_allowed.status_code}")
assert r_admin_allowed.status_code == 200, f"Expected 200 OK, got {r_admin_allowed.status_code}"

print("\n--- 5. Testing Admin Token on User Auth Me ---")
# Admin token cannot authenticate user routes (/api/auth/me expects user_session cookie, not Bearer JWT)
r_user_with_admin = requests.get(f"{BASE_URL}/api/auth/me", headers=headers_admin)
print(f"GET /api/auth/me with Admin Bearer token -> Status: {r_user_with_admin.status_code}")
assert r_user_with_admin.status_code == 401, f"Expected 401, got {r_user_with_admin.status_code}"

print("\n--- ALL READ-ONLY ROLE ISOLATION ASSERTIONS PASSED! ---")
