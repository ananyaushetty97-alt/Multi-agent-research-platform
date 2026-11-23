"""
End-to-end integration test verifying:
1. LLM-as-a-judge quality score and report_id returned for each generated report.
2. User submitting reviews for generated reports (POST /api/reviews).
3. Monograph review isolation across multiple turns / distinct reports.
4. User review visibility in the admin dashboard:
   - GET /api/admin/audit/user-activity (User Activity Logs table)
   - GET /api/admin/quality/human-reviews (Human reviews dataset & calibration)
   - GET /api/admin/quality/summary (Human reviews count)
"""
import uuid
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from api.main import app
from admin_backend.security.tokens import create_access_token
from user_auth.chat_storage import InMemoryChatReviewStorage
import user_auth.chat_routes as chat_routes


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def test_user(client):
    """Register and log in a test user, returning auth cookies."""
    username = f"reviewer_{uuid.uuid4().hex[:6]}"
    email = f"{username}@example.com"
    password = "TestPassword123!"

    headers = {"X-Requested-With": "XMLHttpRequest"}
    reg_resp = client.post(
        "/api/auth/register",
        json={
            "name": username,
            "email": email,
            "password": password,
            "confirm_password": password,
        },
        headers=headers,
    )
    assert reg_resp.status_code == 200, reg_resp.text
    cookies = reg_resp.cookies
    return {"username": username, "email": email, "cookies": cookies, "headers": headers}


@pytest.fixture
def admin_headers():
    token = create_access_token(user_id="admin-001", username="admin_reviewer", role="admin")
    return {"Authorization": f"Bearer {token}"}


def test_generate_returns_report_id_and_quality_score(client):
    """
    Verify that report generation produces a distinct report_id and
    an automated LLM-as-a-judge quality score for the user dashboard.
    """
    fake_score = {
        "overall": 8.7,
        "relevance": 9,
        "accuracy": 8,
        "clarity": 9,
        "comment": "Comprehensive research monograph with strong evidence.",
    }

    with patch("api.integration.run_pipeline") as mock_pipeline, \
         patch("api.main.grade_report", return_value=fake_score), \
         patch("api.main.check_input", return_value=(True, "")):
        
        mock_pipeline.return_value = {
            "report": "## Executive Summary\n\nQuantum key distribution advances secure networks. " * 5,
            "sources": [{"title": "QKD Review", "url": "https://example.com/qkd"}],
            "intent": "NEW_TOPIC",
            "search_count": 3,
        }

        resp = client.post("/generate", json={"topic": "Quantum Key Distribution"})
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert "report_id" in data
        assert data["report_id"] is not None
        assert len(data["report_id"]) > 5

        assert "score" in data
        assert data["score"] is not None
        assert data["score"]["overall"] == 8.7
        assert data["score"]["relevance"] == 9
        assert data["score"]["accuracy"] == 8
        assert data["score"]["clarity"] == 9
        assert "comment" in data["score"]


def test_user_can_submit_review_and_visible_in_admin_dashboard(client, test_user, admin_headers):
    """
    End-to-end verification:
    1. User submits review for a generated monograph.
    2. User can retrieve their submitted review.
    3. Admin can see the review in User Activity Logs (/api/admin/audit/user-activity).
    4. Admin can see the review in Quality Human Reviews (/api/admin/quality/human-reviews).
    5. Admin quality summary reflects the review count.
    """
    rep_id_1 = str(uuid.uuid4())
    topic_1 = "Quantum Computing in Drug Discovery"

    # User submits review
    review_payload = {
        "report_id": rep_id_1,
        "relevance": 9,
        "accuracy": 8,
        "clarity": 10,
        "comment": "Clear explanations of molecular simulation algorithms.",
        "topic": topic_1,
    }
    rev_resp = client.post(
        "/api/reviews",
        json=review_payload,
        cookies=test_user["cookies"],
        headers=test_user["headers"],
    )
    assert rev_resp.status_code in (200, 201), rev_resp.text
    rev_data = rev_resp.json()
    assert rev_data["report_id"] == rep_id_1
    assert rev_data["relevance"] == 9
    assert rev_data["accuracy"] == 8
    assert rev_data["clarity"] == 10

    # User can retrieve their submitted review
    mine_resp = client.get("/api/reviews/mine", cookies=test_user["cookies"], headers=test_user["headers"])
    assert mine_resp.status_code == 200
    my_reviews = mine_resp.json()
    assert any(r["report_id"] == rep_id_1 for r in my_reviews)

    # Admin retrieves User Activity Logs (Tab 7)
    act_resp = client.get("/api/admin/audit/user-activity", headers=admin_headers)
    assert act_resp.status_code == 200, act_resp.text
    user_activities = act_resp.json()
    
    # Check that the review was logged in user activity with topic and details
    matching_act = [
        a for a in user_activities
        if a.get("details", {}).get("report_id") == rep_id_1 or (topic_1 in (a.get("topic") or ""))
    ]
    assert len(matching_act) > 0, f"Review not found in user activity logs: {user_activities}"
    assert "9/8/10" in matching_act[0]["topic"]

    # Admin retrieves Quality Human Reviews (Tab 4)
    q_resp = client.get("/api/admin/quality/human-reviews", headers=admin_headers)
    assert q_resp.status_code == 200, q_resp.text
    human_reviews = q_resp.json()
    matching_hr = [r for r in human_reviews if r.get("report_id") == rep_id_1 or r.get("topic") == topic_1]
    assert len(matching_hr) > 0, f"Review not found in admin quality human reviews: {human_reviews}"
    assert matching_hr[0]["overall"] == 9.0  # round((9+8+10)/3, 1) = 9.0
    assert "(user)" in matching_hr[0]["reviewer_username"]
    assert matching_hr[0]["feedback_notes"] == "Clear explanations of molecular simulation algorithms."

    # Admin retrieves Quality Summary
    sum_resp = client.get("/api/admin/quality/summary", headers=admin_headers)
    assert sum_resp.status_code == 200
    assert sum_resp.json()["human_reviews_count"] >= 1


def test_multiple_report_reviews_isolated_per_turn(client, test_user):
    """
    Verify that each report generated receives its own distinct review
    and subsequent turns in a conversation do not overwrite previous turn reviews.
    """
    rep_id_turn1 = str(uuid.uuid4())
    rep_id_turn2 = str(uuid.uuid4())

    # Submit review for turn 1
    resp1 = client.post(
        "/api/reviews",
        json={
            "report_id": rep_id_turn1,
            "relevance": 10,
            "accuracy": 9,
            "clarity": 9,
            "topic": "Turn 1: Solar Cells",
            "comment": "First turn review",
        },
        cookies=test_user["cookies"],
        headers=test_user["headers"],
    )
    assert resp1.status_code in (200, 201)

    # Submit review for turn 2 (different report_id in same chat)
    resp2 = client.post(
        "/api/reviews",
        json={
            "report_id": rep_id_turn2,
            "relevance": 7,
            "accuracy": 8,
            "clarity": 7,
            "topic": "Turn 2: Perovskite Efficiency",
            "comment": "Second turn review",
        },
        cookies=test_user["cookies"],
        headers=test_user["headers"],
    )
    assert resp2.status_code in (200, 201)

    # Both reviews exist independently
    mine = client.get("/api/reviews/mine", cookies=test_user["cookies"], headers=test_user["headers"]).json()
    ids = [r["report_id"] for r in mine]
    assert rep_id_turn1 in ids
    assert rep_id_turn2 in ids

    rev1 = client.get(f"/api/reviews/{rep_id_turn1}", cookies=test_user["cookies"], headers=test_user["headers"]).json()
    rev2 = client.get(f"/api/reviews/{rep_id_turn2}", cookies=test_user["cookies"], headers=test_user["headers"]).json()
    assert rev1["relevance"] == 10
    assert rev2["relevance"] == 7


def test_postgres_storage_upsert_and_retrieve():
    """
    Direct verification of PostgresChatReviewStorage against the live PostgreSQL database:
    - upsert_review
    - get_user_review
    - list_user_reviews
    - list_all_reviews
    """
    from user_auth.config import settings
    from user_auth.chat_storage import PostgresChatReviewStorage
    import psycopg

    try:
        conn = psycopg.connect(settings.postgres_dsn, connect_timeout=3)
        row = conn.execute("SELECT id FROM public.app_users LIMIT 1").fetchone()
        conn.close()
        if not row:
            pytest.skip("No users in app_users to test FK")
        user_id = str(row[0])
    except Exception as e:
        pytest.skip(f"PostgreSQL not accessible: {e}")

    store = PostgresChatReviewStorage(settings.postgres_dsn)
    report_id = f"pg-rep-{uuid.uuid4().hex[:8]}"

    # Upsert
    rev = store.upsert_review(
        user_id=user_id,
        report_id=report_id,
        relevance=10,
        accuracy=9,
        clarity=10,
        comment="PostgreSQL live store verification.",
        topic="PostgreSQL Integration Topic",
    )
    assert rev is not None
    assert rev["report_id"] == report_id
    assert rev["relevance"] == 10

    # Get single
    fetched = store.get_user_review(user_id=user_id, report_id=report_id)
    assert fetched is not None
    assert fetched["report_id"] == report_id
    assert fetched["accuracy"] == 9
    assert fetched["comment"] == "PostgreSQL live store verification."

    # List user
    user_list = store.list_user_reviews(user_id=user_id)
    assert any(r["report_id"] == report_id for r in user_list)

    # List all
    all_list = store.list_all_reviews(limit=20)
    assert any(r["report_id"] == report_id for r in all_list)


def test_guest_user_can_submit_review_and_visible_in_admin(client, admin_headers):
    """
    Verify that an unauthenticated user in user mode can submit a review,
    and it successfully registers and appears in the admin dashboard.
    """
    rep_id = str(uuid.uuid4())
    topic = "Guest User Monograph on Fusion Energy"

    headers = {"X-Requested-With": "XMLHttpRequest"}
    resp = client.post(
        "/api/reviews",
        json={
            "report_id": rep_id,
            "relevance": 9,
            "accuracy": 9,
            "clarity": 8,
            "topic": topic,
            "comment": "Submitted as guest in user mode.",
        },
        headers=headers,
    )
    assert resp.status_code in (200, 201), resp.text
    data = resp.json()
    assert data["report_id"] == rep_id

    # Check admin quality human reviews
    q_resp = client.get("/api/admin/quality/human-reviews", headers=admin_headers)
    assert q_resp.status_code == 200
    matching = [r for r in q_resp.json() if r.get("report_id") == rep_id]
    assert len(matching) > 0
    assert "(user)" in matching[0]["reviewer_username"]

    # Check admin user activity journal
    act_resp = client.get("/api/admin/audit/user-activity", headers=admin_headers)
    assert act_resp.status_code == 200
    matching_act = [a for a in act_resp.json() if a.get("details", {}).get("report_id") == rep_id]
    assert len(matching_act) > 0
    assert matching_act[0]["username"] == "guest"


