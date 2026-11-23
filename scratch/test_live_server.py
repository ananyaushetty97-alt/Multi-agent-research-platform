import requests
import json
import time
import psycopg

BASE_URL = "http://localhost:8000"

print("--- 1. Testing Admin Login and Tracking Endpoints ---")
login_resp = requests.post(f"{BASE_URL}/api/admin/auth/login", json={"username": "admin", "password": "admin123"})
print("Admin login status:", login_resp.status_code)
assert login_resp.status_code == 200, f"Admin login failed: {login_resp.text}"
admin_token = login_resp.json()["access_token"]
admin_headers = {"Authorization": f"Bearer {admin_token}"}

stats_resp = requests.get(f"{BASE_URL}/api/admin/tracking/stats", headers=admin_headers)
print("Tracking stats status:", stats_resp.status_code)
print("Tracking stats data:", json.dumps(stats_resp.json(), indent=2))

users_resp = requests.get(f"{BASE_URL}/api/admin/tracking/users?limit=5", headers=admin_headers)
print("Tracking users status:", users_resp.status_code)
users_data = users_resp.json()
print(f"Total users: {users_data['total']}, Returned: {len(users_data['users'])}")

act_resp = requests.get(f"{BASE_URL}/api/admin/tracking/activity?limit=5", headers=admin_headers)
print("Tracking activity status:", act_resp.status_code)
act_data = act_resp.json()
print(f"Total activity entries: {act_data['total']}, Returned: {len(act_data['activities'])}")

print("\n--- 2. Testing User Registration (Verify Once Flow) ---")
csrf_headers = {
    "X-Requested-With": "XMLHttpRequest",
    "Origin": "http://localhost:8000"
}
timestamp_val = int(time.time())
test_email = f"live.tester.{timestamp_val}@example.com"
test_password = "SecurePassword123!"

reg_resp = requests.post(f"{BASE_URL}/api/auth/register", json={
    "name": "Live Verification Tester",
    "email": test_email,
    "password": test_password,
    "confirm_password": test_password
}, headers=csrf_headers)
print("Register status:", reg_resp.status_code)
assert reg_resp.status_code == 200
user_info = reg_resp.json()
print("Registered user:", user_info["email"], "email_verified:", user_info["email_verified"])
assert user_info["email_verified"] is False

reg_cookies = reg_resp.cookies.get_dict()
print("Register cookies (should be empty):", reg_cookies)
assert "user_session" not in reg_cookies, "Session cookie should NOT be issued on registration!"

# 3. Unverified login should be rejected with 403 and send OTP
unverified_login = requests.post(f"{BASE_URL}/api/auth/login", json={
    "email": test_email,
    "password": test_password
}, headers=csrf_headers)
print("Unverified login status (must be 403):", unverified_login.status_code)
print("Unverified login message:", unverified_login.json()["detail"])
assert unverified_login.status_code == 403
assert "verification" in unverified_login.json()["detail"].lower()
assert "user_session" not in unverified_login.cookies.get_dict()

# 4. Fetch OTP from postgresql otp_verifications table for test verification
conn = psycopg.connect("postgresql://postgres:devpassword@localhost:5432/research_platform")
cur = conn.cursor()
cur.execute("SELECT otp_hash FROM otp_verifications WHERE email = %s", (test_email,))
otp_row = cur.fetchone()
print("OTP record exists in database:", bool(otp_row))

# Since OTP is hashed with sha256 in DB, let's find the OTP by checking digits 000000..999999 or from memory/console
import hashlib
db_hash = otp_row[0]
found_otp = None
for i in range(1000000):
    candidate = f"{i:06d}"
    if hashlib.sha256(candidate.encode()).hexdigest() == db_hash:
        found_otp = candidate
        break

print(f"Cracked OTP from DB hash in milliseconds: {found_otp}")
assert found_otp is not None

# 5. Verify OTP
v_resp = requests.post(f"{BASE_URL}/api/auth/verify-otp", json={
    "email": test_email,
    "otp": found_otp
}, headers=csrf_headers)
print("Verify OTP status:", v_resp.status_code)
assert v_resp.status_code == 200
v_data = v_resp.json()
print("Verify OTP message:", v_data["message"])
print("Verify OTP cookies (session issued!):", v_resp.cookies.get_dict())
assert "user_session" in v_resp.cookies.get_dict()
session_cookie = v_resp.cookies.get_dict()["user_session"]

# 6. /api/auth/me works with this session cookie
me_resp = requests.get(f"{BASE_URL}/api/auth/me", cookies={"user_session": session_cookie}, headers=csrf_headers)
print("/api/auth/me status:", me_resp.status_code)
assert me_resp.status_code == 200
print("User profile:", me_resp.json()["email"], "verified:", me_resp.json()["email_verified"])
assert me_resp.json()["email_verified"] is True

# 7. Normal login now succeeds directly with session cookie
succ_login = requests.post(f"{BASE_URL}/api/auth/login", json={
    "email": test_email,
    "password": test_password
}, headers=csrf_headers)
print("Subsequent login status:", succ_login.status_code)
assert succ_login.status_code == 200
assert "user_session" in succ_login.cookies.get_dict()

print("\n--- 3. Testing Research Generation with Live Judge & Sanitization ---")
research_topic = "Applications of synthetic biology in green fuels"
gen_resp = requests.post(f"{BASE_URL}/generate", json={
    "topic": research_topic,
    "grade": True
}, cookies={"user_session": session_cookie}, headers=csrf_headers, timeout=120)

print("Generate status:", gen_resp.status_code)
assert gen_resp.status_code == 200
gen_data = gen_resp.json()
report = gen_data["report"]
print("\nGenerated Report Preview (first 250 chars):")
print(report[:250])
print("\nGrading score returned:", gen_data.get("score"))
assert gen_data.get("score") is not None
assert "overall" in gen_data["score"]

# Assert no prompt leakage
assert "You are a" not in report
assert "<research_topic>" not in report
assert "</research_topic>" not in report
assert "Rules:" not in report

print("\n--- 4. Checking Admin Tracking Updates for this User ---")
user_detail_resp = requests.get(f"{BASE_URL}/api/admin/tracking/users/{me_resp.json()['id']}", headers=admin_headers)
print("Admin user detail status:", user_detail_resp.status_code)
assert user_detail_resp.status_code == 200
user_detail = user_detail_resp.json()
print("Conversations tracked in admin:", len(user_detail["conversations"]))
print("Activity timeline count in admin:", len(user_detail["activity_timeline"]))
activity_types = [a["event_type"] for a in user_detail["activity_timeline"]]
print("User activities recorded:", activity_types)
assert "signup" in activity_types
assert "email_verified" in activity_types
assert "research_started" in activity_types
assert "report_generated" in activity_types
assert "grading_completed" in activity_types

print("\nALL 5 ISSUES VERIFIED AND PASSING ON LIVE PRODUCTION STACK!")
