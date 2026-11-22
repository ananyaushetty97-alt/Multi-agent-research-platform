"""
Verify user review flow via POST /api/reviews:
- Confirms review submission still works.
- Confirms quality_service._human_reviews is NOT populated by user review submission.
- Uses a transaction rollback or temporary throwaway to ensure the 9 baseline rows are preserved.
"""
import sys
import uuid
import psycopg
from psycopg.rows import dict_row

sys.path.insert(0, r"c:\Projects\Multi-agent-research-platform")

from fastapi.testclient import TestClient
from api.main import app
from admin_backend.services.quality_service import quality_service
from user_auth.dependencies import get_optional_user, get_current_user
from user_auth.models import UserResponse

client = TestClient(app, raise_server_exceptions=True)

# Mock user for authentication using a valid user_id from app_users
dummy_user = UserResponse(
    id="defe3469-b388-4225-8e7a-e20353cc51e7",
    email="sudeep@gmail.com",
    role="user",
    username="sudeep",
    name="Sudeep",
    avatar_url=None,
    auth_provider="google",
    is_active=True,
)

app.dependency_overrides[get_optional_user] = lambda: dummy_user
app.dependency_overrides[get_current_user] = lambda: dummy_user

# Ensure in-memory is empty
quality_service._human_reviews.clear()

try:
    # Read baseline count before
    with psycopg.connect(quality_service.get_postgres_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM public.report_reviews;")
            count_before = cur.fetchone()[0]

    # Submit a user review
    temp_report_id = f"test-flow-{uuid.uuid4().hex[:8]}"
    payload = {
        "report_id": temp_report_id,
        "topic": "Test User Review Flow",
        "relevance": 9,
        "accuracy": 8,
        "clarity": 10,
        "comment": "Testing user review persistence without admin in-memory mirror",
    }

    res = client.post(
        "/api/reviews",
        json=payload,
        headers={"X-Requested-With": "XMLHttpRequest"}
    )
    print("POST /api/reviews status:", res.status_code)
    assert res.status_code in (200, 201), f"Expected 200/201, got {res.status_code}: {res.text}"
    review_data = res.json()
    print("Review submitted successfully:", review_data.get("id"))

    # Assert user review was NOT added to quality_service._human_reviews
    print("quality_service._human_reviews length:", len(quality_service._human_reviews))
    assert len(quality_service._human_reviews) == 0, "User review MUST NOT be mirrored to quality_service._human_reviews!"

    # Clean up the single temporary test row so baseline remains untouched
    with psycopg.connect(quality_service.get_postgres_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public.report_reviews WHERE report_id LIKE %s;", ("test-flow-%",))
            conn.commit()
            cur.execute("SELECT count(*) FROM public.report_reviews;")
            count_after = cur.fetchone()[0]

    print(f"Row count before: {count_before}, row count after cleanup: {count_after}")
    assert count_before == count_after == 9, "PostgreSQL baseline row count must remain 9!"

    print("USER REVIEW FLOW AND MIRROR REMOVAL VERIFIED SUCCESSFULLY!")

finally:
    app.dependency_overrides.pop(get_optional_user, None)
    app.dependency_overrides.pop(get_current_user, None)
