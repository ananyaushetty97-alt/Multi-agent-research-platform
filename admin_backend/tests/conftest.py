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
    return temp_dir


@pytest.fixture
def admin_token():
    return create_access_token(user_id="test-admin-1", username="admin_tester", role="admin")


@pytest.fixture
def user_token():
    return create_access_token(user_id="test-user-1", username="regular_user", role="user")


@pytest.fixture
def test_app():
    """Isolated FastAPI test application mounting admin_router."""
    app = FastAPI(title="Admin Test Harness")
    app.include_router(admin_router)
    return app


@pytest.fixture
def client(test_app):
    return TestClient(test_app)
