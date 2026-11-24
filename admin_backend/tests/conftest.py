"""
Pytest fixtures for admin backend isolated tests.
"""
import os
import sys
import tempfile
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure root directory is on PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from admin_backend.config import settings
from admin_backend.router import admin_router
from admin_backend.security.tokens import create_access_token


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Ensure test runs in a clean temporary directory and does not alter production logs."""
    temp_dir = tempfile.mkdtemp()
    monkeypatch.setattr(settings, "admin_audit_log_path", os.path.join(temp_dir, "admin_audit.jsonl"))
    monkeypatch.setattr(settings, "admin_traces_log_path", os.path.join(temp_dir, "admin_traces.jsonl"))
    monkeypatch.setattr(settings, "admin_safety_log_path", os.path.join(temp_dir, "admin_safety.jsonl"))
    monkeypatch.setattr(settings, "scores_log_path", os.path.join(temp_dir, "scores.jsonl"))
    monkeypatch.setattr(settings, "redteam_results_path", os.path.join(temp_dir, "redteam_results.json"))
    monkeypatch.setattr(settings, "admin_secret_key", "test-secret-key-for-unit-testing-32-bytes-long!")
    monkeypatch.setattr(settings, "admin_jwt_secret", "test-secret-key-for-unit-testing-32-bytes-long!")

    # Provide mock storage resolving test tokens
    from admin_backend.security import dependencies
    real_storage = dependencies._get_user_storage()

    class MockUserStorage:
        def get_by_id(self, user_id):
            if str(user_id) == "test-admin-1":
                return {"id": "test-admin-1", "username": "admin_tester", "role": "admin", "is_active": True}
            if str(user_id) == "test-user-1":
                return {"id": "test-user-1", "username": "regular_user", "role": "user", "is_active": True}
            try:
                return real_storage.get_by_id(user_id)
            except Exception:
                return None

        def get_by_username(self, username):
            if username == "admin_tester":
                return {"id": "test-admin-1", "username": "admin_tester", "role": "admin", "is_active": True}
            if username == "regular_user":
                return {"id": "test-user-1", "username": "regular_user", "role": "user", "is_active": True}
            try:
                return real_storage.get_by_username(username)
            except Exception:
                return None

        def get_admin_by_email(self, email):
            try:
                return real_storage.get_admin_by_email(email)
            except Exception:
                return None

        def update_admin_login(self, *args, **kwargs):
            try:
                return real_storage.update_admin_login(*args, **kwargs)
            except Exception:
                return None

    monkeypatch.setattr(dependencies, "_user_storage", MockUserStorage())
    return temp_dir


@pytest.fixture
def admin_token():
    return create_access_token(user_id="test-admin-1", username="admin_tester", role="admin")


@pytest.fixture
def user_token():
    return create_access_token(user_id="test-user-1", username="regular_user", role="user")


@pytest.fixture
def test_app():
    """Isolated FastAPI test application mounting admin_router and user_auth_router."""
    from user_auth.routes import router as user_auth_router
    app = FastAPI(title="Admin Test Harness")
    app.include_router(admin_router)
    app.include_router(user_auth_router, prefix="/api/auth")
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)
