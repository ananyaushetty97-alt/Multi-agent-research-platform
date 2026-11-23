"""
End-to-end integration test asserting that for a registered & verified user:
1. Research query generates report
2. Report contains NO leaked prompt text or system instructions
3. Grading completes with valid numerical scores
4. Activity logs record research_started, report_generated, grading_completed, and research_completed
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from api.main import app
from user_auth.config import settings
from user_auth.service import auth_service
from user_auth.storage import InMemoryUserAuthStorage, set_user_auth_storage
from user_auth.security import auth_security_manager


@pytest.fixture
def mock_storage(monkeypatch):
    mem_storage = InMemoryUserAuthStorage()
    set_user_auth_storage(mem_storage)
    auth_service._storage_override = mem_storage
    auth_security_manager.reset()
    settings.auth_storage_backend = "memory"
    settings.require_login = True
    return mem_storage


def test_research_query_end_to_end_sanitization_and_grading(mock_storage):
    client = TestClient(app)
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "http://localhost:8000",
        "Host": "localhost:8000",
    }

    # 1. Register user
    reg_resp = client.post("/api/auth/register", json={
        "name": "Grace Hopper",
        "email": "grace.hopper@example.com",
        "password": "CompilerPassword123",
        "confirm_password": "CompilerPassword123"
    }, headers=headers)
    assert reg_resp.status_code == 200
    user_id = reg_resp.json()["id"]

    # 2. Verify OTP to obtain session cookie
    from user_auth.email_service import email_service
    sent = email_service.sent_emails[-1]
    import re
    otp = re.search(r"\b(\d{6})\b", sent["text"]).group(1)

    v_resp = client.post("/api/auth/verify-otp", json={
        "email": "grace.hopper@example.com",
        "otp": otp
    }, headers=headers)
    assert v_resp.status_code == 200
    cookie = v_resp.cookies[settings.session_cookie_name]

    # 3. Execute research query with mock LLM pipeline
    mock_pipeline_result = {
        "topic": "Compilers and Programming Languages",
        "summary": "Compilers translate high-level source code to executable machine instructions.",
        "search_results": [{"title": "History of Compilers", "url": "https://example.com/compilers"}],
        "report": (
            "You are a professional academic research report writer. Write a comprehensive report.\n"
            "<research_topic>Compilers and Programming Languages</research_topic>\n"
            "# Compilers and High-Level Programming Languages\n\n"
            "Compilers translate source code into optimized machine code [1].\n\n"
            "## Sources\n- [1] History of Compilers — https://example.com/compilers"
        ),
        "intent": "new_research",
        "is_verified": True,
    }

    mock_judge_score = {
        "relevance": 9,
        "accuracy": 8,
        "clarity": 9,
        "overall": 8.7,
        "comment": "Accurate and clearly explained monograph.",
    }

    with patch("api.integration.run_pipeline", return_value=mock_pipeline_result):
        with patch("api.main.grade_report", return_value=mock_judge_score):
            gen_resp = client.post("/generate", json={
                "topic": "Compilers and Programming Languages",
                "grade": True
            }, headers={**headers, "Cookie": f"{settings.session_cookie_name}={cookie}"})

    assert gen_resp.status_code == 200
    gen_data = gen_resp.json()

    # Assert report was sanitized (no prompt leakage)
    report_text = gen_data["report"]
    assert "You are a professional academic research report writer" not in report_text
    assert "<research_topic>" not in report_text
    assert "</research_topic>" not in report_text
    assert "# Compilers and High-Level Programming Languages" in report_text

    # Assert grading succeeded with overall score
    assert gen_data["score"] is not None
    assert gen_data["score"]["overall"] == 8.7

    # Assert activity logs recorded all lifecycle events
    logs = mock_storage.query_activity_logs(user_id=user_id, limit=20)
    event_types = [entry["event_type"] for entry in logs]
    assert "signup" in event_types
    assert "email_verified" in event_types
    assert "research_started" in event_types
    assert "report_generated" in event_types
    assert "grading_completed" in event_types
    assert "research_completed" in event_types
