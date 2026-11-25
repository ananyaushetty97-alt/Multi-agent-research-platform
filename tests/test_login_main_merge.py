"""
Tests for the parts that connect the login branch (user accounts, Google admin sign-in)
with main (admin password login, file uploads, file-saved human reviews, persistent audit log).
"""
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from api.main import app
from admin_backend.models.audit import AuditAction, AuditLogEntry, AuditLogFilter
from admin_backend.routes import auth_routes
from admin_backend.services.quality_service import QualityService
from admin_backend.storage.persistent import PersistentAuditStorage
from user_auth.chat_storage import InMemoryChatReviewStorage, set_chat_review_storage
from user_auth.config import settings as user_settings
from user_auth.dependencies import get_optional_user
from user_auth.models import UserResponse
from user_auth.storage import InMemoryUserAuthStorage, set_user_auth_storage

HEADERS = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
def chat_store():
    store = InMemoryChatReviewStorage()
    set_chat_review_storage(store)
    set_user_auth_storage(InMemoryUserAuthStorage())
    user_settings.require_login = False
    yield store
    set_chat_review_storage(None)
    set_user_auth_storage(None)
    app.dependency_overrides.clear()


@pytest.fixture
def client(monkeypatch):
    from admin_backend.config import settings as admin_settings
    monkeypatch.setattr(admin_settings, "admin_jwt_secret", "merge-test-secret-key-at-least-32-characters!")
    return TestClient(app)


def _signed_in_as(user_id):
    user = UserResponse(id=user_id, name="Test User", email="tester@example.com", username="tester",
                        email_verified=True)
    app.dependency_overrides[get_optional_user] = lambda: user
    return user


# ---------------------------------------------------------------- admin password login (main)

def test_default_admin_password_login_still_works(client):
    resp = client.post("/api/admin/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "admin"
    assert body["access_token"]

    me = client.get("/api/admin/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["role"] == "admin"


def test_password_login_rejects_non_admin_accounts(client):
    resp = client.post("/api/admin/auth/login", json={"username": "user", "password": "user123"})
    assert resp.status_code == 401


def test_password_login_rejects_wrong_password(client):
    resp = client.post("/api/admin/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_google_admin_config_endpoint_exists(client):
    resp = client.get("/api/admin/auth/config")
    assert resp.status_code == 200
    assert "google_client_id" in resp.json()


def test_account_store_checks_memory_then_postgres():
    store = auth_routes.AdminAccountStore()

    class FakePostgres:
        def get_by_username(self, name):
            if name == "google-admin":
                return {"id": "g1", "username": "google-admin", "role": "admin"}
            return None

        def get_by_id(self, uid):
            if uid == "g1":
                return {"id": "g1", "username": "google-admin", "role": "admin"}
            return None

        def get_admin_by_email(self, email):
            return {"id": "g1", "email": email, "role": "admin"}

    store._postgres = FakePostgres()
    store.create_user({"id": "m1", "username": "local", "email": "l@x.com", "hashed_password": "x",
                       "role": "admin", "is_active": True, "created_at": datetime.now(timezone.utc)})
    assert store.get_by_username("local")["id"] == "m1"
    assert store.get_by_username("google-admin")["id"] == "g1"
    assert store.get_by_id("g1")["id"] == "g1"
    assert store.get_admin_by_email("a@b.com")["id"] == "g1"
    assert store.get_by_username("nobody") is None


# ---------------------------------------------------------------- file uploads (main) + accounts (login)

def _pipeline_patches(report_text, history=None):
    return [
        patch("api.main.parts.run_pipeline", return_value={"report": report_text, "intent": "new_research"}),
        patch("api.main.parts.get_history", return_value=history or []),
        patch("api.main.parts.save_to_ltm", return_value=None),
        patch("api.main.check_input", return_value=(True, "ok")),
        patch("api.main.check_output", return_value=(True, "ok")),
        patch("api.main.grade_report", return_value=None),
    ]


def test_file_upload_uses_same_guest_memory_key_as_generate(client, chat_store):
    remembered = []
    patches = _pipeline_patches("File based report.")
    patches.append(patch("api.main.parts.check_cache", return_value=None))
    patches.append(patch("api.main._remember", side_effect=lambda sid, *a, **k: remembered.append(sid)))
    for p in patches:
        p.start()
    try:
        resp = client.post(
            "/generate-with-files",
            data={"topic": "Summarise this", "session_id": "chat-1", "grade": "false"},
            files=[("files", ("notes.txt", b"Some notes about solar microgrids.", "text/plain"))],
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["report_id"]
        # Same key format /generate uses for guests, so a follow-up in this chat finds the report
        assert remembered == ["guest:chat-1"]
    finally:
        for p in patches:
            p.stop()


def test_file_upload_saves_chat_for_signed_in_user(client, chat_store):
    _signed_in_as("user-42")
    cache_calls = []
    patches = _pipeline_patches("Report from uploaded file.")
    patches.append(patch("api.main.parts.check_cache",
                         side_effect=lambda topic, user_id=None: cache_calls.append(user_id)))
    remembered = []
    patches.append(patch("api.main._remember", side_effect=lambda sid, *a, **k: remembered.append(sid)))
    for p in patches:
        p.start()
    try:
        resp = client.post(
            "/generate-with-files",
            data={"topic": "Summarise this", "session_id": "chat-9", "grade": "false"},
            files=[("files", ("paper.txt", b"Text of a paper.", "text/plain"))],
        )
        assert resp.status_code == 200, resp.text
    finally:
        for p in patches:
            p.stop()

    assert cache_calls == ["user-42"]
    assert remembered == ["user:user-42:chat-9"]
    session = chat_store.get_chat_session(user_id="user-42", session_id="chat-9")
    assert session is not None
    assert session["title"] == "paper.txt"
    messages = chat_store.get_chat_messages("chat-9") if hasattr(chat_store, "get_chat_messages") else None
    if messages is not None:
        assert any("paper.txt" in m["content"] for m in messages if m["role"] == "user")


def test_file_upload_requires_login_when_configured(client, chat_store):
    user_settings.require_login = True
    try:
        resp = client.post("/generate-with-files", data={"topic": "x"},
                           files=[("files", ("a.txt", b"abc", "text/plain"))])
        assert resp.status_code == 401
    finally:
        user_settings.require_login = False


# ---------------------------------------------------------------- human reviews (main file + login DB)

def _review_file(tmp_path, rows):
    path = tmp_path / "reviews.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return str(path)


def _row(review_id, name, is_expert=None):
    row = {
        "review_id": review_id, "topic": "Solar microgrids", "reviewer_username": name,
        "review_timestamp": "2026-11-25T10:00:00+00:00", "relevance": 8, "accuracy": 7,
        "clarity": 9, "overall": 8.0,
    }
    if is_expert is not None:
        row["is_expert"] = is_expert
    return row


def test_reviews_without_database_come_from_file_and_are_labelled(tmp_path, chat_store):
    path = _review_file(tmp_path, [_row("r1", "user"), _row("r2", "dr_rao", is_expert=True)])
    svc = QualityService(log_path=str(tmp_path / "none.jsonl"), human_reviews_path=path, postgres_dsn="")
    reviews = svc.list_human_reviews()
    names = sorted(r.reviewer_username for r in reviews)
    assert names == ["dr_rao (expert)", "user (user)"]
    assert svc.count_human_reviews() == 2
    assert svc.get_quality_summary().human_reviews_count == 2


def test_reviews_fall_back_when_database_is_down(tmp_path, chat_store):
    path = _review_file(tmp_path, [_row("r1", "user")])
    svc = QualityService(log_path=str(tmp_path / "none.jsonl"), human_reviews_path=path,
                         postgres_dsn="postgresql://nobody:secret@127.0.0.1:1/none")
    reviews = svc.list_human_reviews()
    assert [r.review_id for r in reviews] == ["r1"]
    assert svc.count_human_reviews() == 1


def test_added_review_is_saved_to_file_and_counted(tmp_path, chat_store):
    path = str(tmp_path / "reviews.jsonl")
    svc = QualityService(log_path=str(tmp_path / "none.jsonl"), human_reviews_path=path, postgres_dsn="")
    svc.add_human_review(topic="T", reviewer_username="user", relevance=8, accuracy=8, clarity=8,
                         is_expert=False)
    assert svc.count_human_reviews() == 1
    reloaded = QualityService(log_path=str(tmp_path / "none.jsonl"), human_reviews_path=path, postgres_dsn="")
    assert len(reloaded.list_human_reviews()) == 1
    assert reloaded.list_human_reviews()[0].reviewer_username == "user (user)"


def test_user_portal_review_endpoint_marks_review_as_user(client, chat_store, monkeypatch, tmp_path):
    svc = QualityService(log_path=str(tmp_path / "none.jsonl"),
                         human_reviews_path=str(tmp_path / "reviews.jsonl"), postgres_dsn="")
    monkeypatch.setattr(api_main, "quality_service", svc)
    resp = client.post("/quality/human-reviews", json={"topic": "T", "relevance": 8, "accuracy": 8, "clarity": 8})
    assert resp.status_code == 200
    assert resp.json()["is_expert"] is False


# ---------------------------------------------------------------- audit log filters (login) on main's storage

def test_persistent_audit_storage_supports_partial_actor_and_dates(tmp_path):
    store = PersistentAuditStorage(audit_file_path=str(tmp_path / "audit.jsonl"),
                                   activity_file_path=str(tmp_path / "activity.jsonl"))
    now = datetime.now(timezone.utc)
    for name, when in [("alice@example.com", now - timedelta(days=3)), ("bob@example.com", now)]:
        store.append_audit_entry(AuditLogEntry(
            id=f"id-{name}", timestamp=when.isoformat(), actor_username=name, actor_role="admin",
            action=AuditAction.CONFIG_READ, resource_type="config", status="success",
        ))
    assert [e.actor_username for e in store.query_audit_entries(AuditLogFilter(actor="alice"))] == ["alice@example.com"]
    # exact names still match, as before
    assert len(store.query_audit_entries(AuditLogFilter(actor="bob@example.com"))) == 1
    recent = store.query_audit_entries(AuditLogFilter(start_date=(now - timedelta(days=1)).isoformat()))
    assert [e.actor_username for e in recent] == ["bob@example.com"]
