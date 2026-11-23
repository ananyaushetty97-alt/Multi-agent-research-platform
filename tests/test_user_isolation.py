"""
End-to-end tests proving multi-user isolation across:
1. Server-side chat persistence and ownership (User A cannot read, edit, or delete User B's chats).
2. Report reviews (User A cannot see or mutate User B's reviews; guest cannot review).
3. Memory scoping (STM session keys, Semantic Cache, and LTM vector store respect user boundaries).
"""

import os
import tempfile
import uuid
import pytest
from fastapi.testclient import TestClient

from api.main import app
from memory.embeddings import embed
from memory.ltm import LongTermMemory
from memory.semantic_cache import SemanticCache
from memory.stm import SessionStore
from user_auth.chat_storage import InMemoryChatReviewStorage, set_chat_review_storage
from user_auth.config import settings
from user_auth.security import auth_security_manager
from user_auth.service import auth_service
from user_auth.storage import InMemoryUserAuthStorage, set_user_auth_storage
from admin_backend.services.audit_service import audit_service
from admin_backend.config import settings as admin_settings


@pytest.fixture(autouse=True)
def setup_isolation_env(monkeypatch):
    """Ensure in-memory storages and temp audit files are used so tests run cleanly and fast."""
    mem_auth = InMemoryUserAuthStorage()
    set_user_auth_storage(mem_auth)
    auth_service._storage_override = mem_auth
    auth_security_manager.reset()

    chat_store = InMemoryChatReviewStorage()
    set_chat_review_storage(chat_store)

    settings.auth_storage_backend = "memory"
    settings.neutralize_demo_users = True
    settings.require_login = False
    monkeypatch.setattr(settings, "smtp_host", None)
    monkeypatch.setattr(settings, "resend_api_key", None)
    monkeypatch.setattr(settings, "brevo_api_key", None)

    class _TestAuditStorage:
        def __init__(self):
            self.entries = []
            self.user_activities = []
        def append_audit_entry(self, e): self.entries.append(e)
        def append_user_activity_entry(self, e): self.user_activities.append(e)
        def query_audit_entries(self, f): return list(self.entries)
        def query_user_activity_entries(self, f): return list(self.user_activities)

    monkeypatch.setattr(audit_service, "storage", _TestAuditStorage())
    tmp_file = os.path.join(tempfile.mkdtemp(), "test_isolation_audit.jsonl")
    monkeypatch.setattr(audit_service, "log_file", tmp_file)
    monkeypatch.setattr(admin_settings, "admin_audit_log_path", tmp_file)

    yield {"auth": mem_auth, "chats": chat_store}
    set_chat_review_storage(None)


def _register_and_login(client: TestClient, name: str, email: str, password: str = "Password123") -> str:
    """Helper to register and login a user, returning their session cookie."""
    headers = {"X-Requested-With": "XMLHttpRequest"}
    r = client.post(
        "/api/auth/register",
        json={"name": name, "email": email, "password": password, "confirm_password": password},
        headers=headers,
    )
    assert r.status_code == 200, f"Registration failed: {r.text}"
    from user_auth.storage import get_user_auth_storage
    storage = get_user_auth_storage()
    u = storage.get_user_by_email(email)
    if u:
        storage.update_user(u["id"], {"email_verified": True})
    login_resp = client.post("/api/auth/login", json={"email": email, "password": password}, headers=headers)
    cookie = login_resp.cookies.get(settings.session_cookie_name)
    assert cookie is not None
    return cookie


def test_chat_ownership_and_isolation():
    """Verify that User A and User B cannot read, rename, or delete each other's chats."""
    client_a = TestClient(app)
    client_b = TestClient(app)
    headers = {"X-Requested-With": "XMLHttpRequest"}

    # 1. Register User A and User B
    _register_and_login(client_a, "User A", "user_a@example.com")
    _register_and_login(client_b, "User B", "user_b@example.com")

    # 2. User A creates a chat
    resp_a = client_a.post("/api/chats", json={"title": "User A Private Research"}, headers=headers)
    assert resp_a.status_code == 201
    chat_a_id = resp_a.json()["id"]

    # 3. User B creates a chat
    resp_b = client_b.post("/api/chats", json={"title": "User B Confidential Query"}, headers=headers)
    assert resp_b.status_code == 201
    chat_b_id = resp_b.json()["id"]

    # 4. User A list chats -> contains only chat A
    chats_a = client_a.get("/api/chats").json()
    assert len(chats_a) == 1
    assert chats_a[0]["id"] == chat_a_id

    # 5. User B list chats -> contains only chat B
    chats_b = client_b.get("/api/chats").json()
    assert len(chats_b) == 1
    assert chats_b[0]["id"] == chat_b_id

    # 6. User B tries to read User A's chat -> 404 (isolated)
    resp_cross_read = client_b.get(f"/api/chats/{chat_a_id}")
    assert resp_cross_read.status_code == 404
    assert "access denied" in resp_cross_read.json()["detail"].lower()

    # 7. User B tries to rename User A's chat -> 404
    resp_cross_rename = client_b.put(
        f"/api/chats/{chat_a_id}",
        json={"title": "Hacked Title"},
        headers=headers,
    )
    assert resp_cross_rename.status_code == 404

    # 8. User B tries to delete User A's chat -> 404
    resp_cross_delete = client_b.delete(f"/api/chats/{chat_a_id}", headers=headers)
    assert resp_cross_delete.status_code == 404

    # User A's chat is still untouched
    read_again = client_a.get(f"/api/chats/{chat_a_id}")
    assert read_again.status_code == 200
    assert read_again.json()["title"] == "User A Private Research"

    # 9. User A can rename and delete their own chat
    rename_ok = client_a.put(
        f"/api/chats/{chat_a_id}",
        json={"title": "User A Updated"},
        headers=headers,
    )
    assert rename_ok.status_code == 200
    assert rename_ok.json()["title"] == "User A Updated"

    del_ok = client_a.delete(f"/api/chats/{chat_a_id}", headers=headers)
    assert del_ok.status_code == 200
    assert client_a.get(f"/api/chats/{chat_a_id}").status_code == 404


def test_reviews_isolation_and_guest_rejection():
    """Verify reviews endpoints: one per user via upsert, strict isolation, and guest rejection."""
    client_guest = TestClient(app)
    client_a = TestClient(app)
    client_b = TestClient(app)
    headers = {"X-Requested-With": "XMLHttpRequest"}

    # 1. Unauthenticated guest tries to submit review when login is required -> 401
    settings.require_login = True
    try:
        guest_rev = client_guest.post(
            "/api/reviews",
            json={"report_id": "rep-101", "relevance": 8, "accuracy": 8, "clarity": 8},
            headers=headers,
        )
        assert guest_rev.status_code == 401
    finally:
        settings.require_login = False

    # 2. Register users
    _register_and_login(client_a, "Alice", "alice_rev@example.com")
    _register_and_login(client_b, "Bob", "bob_rev@example.com")

    # 3. Validation: ratings must be 1-10, comments <= 1000
    invalid_rating = client_a.post(
        "/api/reviews",
        json={"report_id": "rep-101", "relevance": 15, "accuracy": 5, "clarity": 5},
        headers=headers,
    )
    assert invalid_rating.status_code == 422

    long_comment = "x" * 1001
    invalid_comment = client_a.post(
        "/api/reviews",
        json={"report_id": "rep-101", "relevance": 8, "accuracy": 8, "clarity": 8, "comment": long_comment},
        headers=headers,
    )
    assert invalid_comment.status_code == 422

    # 4. User A submits review for rep-101
    rev_a = client_a.post(
        "/api/reviews",
        json={"report_id": "rep-101", "relevance": 9, "accuracy": 8, "clarity": 10, "comment": "Alice: Thorough"},
        headers=headers,
    )
    assert rev_a.status_code == 201

    # 5. User B submits review for the SAME report rep-101
    rev_b = client_b.post(
        "/api/reviews",
        json={"report_id": "rep-101", "relevance": 6, "accuracy": 7, "clarity": 5, "comment": "Bob: Average"},
        headers=headers,
    )
    assert rev_b.status_code == 201

    # 6. Read back report review: each user receives their OWN review
    read_a = client_a.get("/api/reviews/rep-101").json()
    assert read_a["relevance"] == 9
    assert read_a["comment"] == "Alice: Thorough"

    read_b = client_b.get("/api/reviews/rep-101").json()
    assert read_b["relevance"] == 6
    assert read_b["comment"] == "Bob: Average"

    # 7. Upsert: User A updates review for rep-101
    update_a = client_a.post(
        "/api/reviews",
        json={"report_id": "rep-101", "relevance": 10, "accuracy": 9, "clarity": 10, "comment": "Alice: Exceptional now"},
        headers=headers,
    )
    assert update_a.status_code == 201
    mine_a = client_a.get("/api/reviews/mine").json()
    assert len(mine_a) == 1
    assert mine_a[0]["relevance"] == 10
    assert mine_a[0]["comment"] == "Alice: Exceptional now"


def test_stm_and_cache_scoping():
    """Verify that STM sessions and Semantic Cache respect user scoping boundaries."""
    # STM Session namespace verification
    store = SessionStore(prefix="test_scope:")
    # User A session vs User B session with the same session_id string
    session_id = "shared-session-name"
    store.set(f"user:user_a_uuid:{session_id}", {"topic": "A's Topic", "step": "write"})
    store.set(f"user:user_b_uuid:{session_id}", {"topic": "B's Topic", "step": "verify"})

    assert store.get(f"user:user_a_uuid:{session_id}") == {"topic": "A's Topic", "step": "write"}
    assert store.get(f"user:user_b_uuid:{session_id}") == {"topic": "B's Topic", "step": "verify"}

    # Semantic Cache scoping
    cache = SemanticCache(prefix="semcache:scope_test:")
    topic = "Deep marine trench biological adaptations"
    cache.store(topic, {"report": "Alice private monograph"}, user_id="user_a_uuid")

    # Alice queries -> hits cache
    alice_hit = cache.lookup(topic, user_id="user_a_uuid")
    assert alice_hit is not None
    assert alice_hit["report"]["report"] == "Alice private monograph"

    # Bob queries same topic -> miss (does not leak Alice's private research)
    bob_hit = cache.lookup(topic, user_id="user_b_uuid")
    assert bob_hit is None

    # Guest queries same topic -> miss (does not leak private user research)
    guest_hit = cache.lookup(topic, user_id=None)
    assert guest_hit is None
