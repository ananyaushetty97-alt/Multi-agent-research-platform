"""
Unit tests for health service dependency probes.
Uses mocking to test all failure and success branches without external network calls.
"""
from unittest.mock import MagicMock, patch
import httpx

from admin_backend.models.health import ServiceStatus
from admin_backend.services.health_service import HealthService


def test_process_health():
    svc = HealthService()
    proc = svc.check_process()
    assert proc.pid > 0
    assert proc.uptime_seconds >= 0
    assert proc.python_version


def test_redis_probe_unreachable():
    svc = HealthService()
    # Test pointing to invalid port
    with patch("redis.Redis.from_url") as mock_from_url:
        mock_client = MagicMock()
        mock_client.ping.side_effect = ConnectionRefusedError("Connection refused")
        mock_from_url.return_value = mock_client

        res = svc.check_redis()
        assert res.name == "redis"
        assert res.status == ServiceStatus.UNAVAILABLE
        assert "Connection refused" in (res.error or "")


def test_redis_probe_healthy():
    svc = HealthService()
    with patch("redis.Redis.from_url") as mock_from_url:
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_from_url.return_value = mock_client

        res = svc.check_redis()
        assert res.status == ServiceStatus.HEALTHY
        assert res.latency_ms is not None


def test_postgres_probe_unconfigured(monkeypatch):
    from admin_backend.config import settings
    monkeypatch.setattr(settings, "postgres_dsn", "")
    svc = HealthService()
    res = svc.check_postgres()
    assert res.status == ServiceStatus.NOT_CONFIGURED


def test_groq_probe_not_configured(monkeypatch):
    from admin_backend.config import settings
    monkeypatch.setattr(settings, "groq_api_key", None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    svc = HealthService()
    res = svc.check_groq()
    assert res.status == ServiceStatus.NOT_CONFIGURED


def test_ollama_probe_reachable():
    svc = HealthService()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"models": [{"name": "qwen2.5:7b"}]}

    with patch.object(httpx.Client, "get", return_value=mock_resp):
        res = svc.check_ollama()
        assert res.status == ServiceStatus.HEALTHY
        assert "qwen2.5:7b" in res.details["available_models"]


def test_ollama_probe_unreachable():
    svc = HealthService()
    with patch.object(httpx.Client, "get", side_effect=httpx.ConnectError("Connection refused")):
        res = svc.check_ollama()
        assert res.status == ServiceStatus.UNAVAILABLE
        assert "Connection refused" in (res.error or "")


def test_full_health_synthesis():
    svc = HealthService()
    from admin_backend.models.health import DependencyCheckResult
    with patch.object(svc, "check_redis", return_value=DependencyCheckResult(name="redis", status=ServiceStatus.HEALTHY)), \
         patch.object(svc, "check_postgres", return_value=DependencyCheckResult(name="postgres", status=ServiceStatus.HEALTHY)), \
         patch.object(svc, "check_groq", return_value=DependencyCheckResult(name="groq", status=ServiceStatus.HEALTHY)), \
         patch.object(svc, "check_ollama", return_value=DependencyCheckResult(name="ollama", status=ServiceStatus.HEALTHY)), \
         patch.object(svc, "check_tavily", return_value=DependencyCheckResult(name="tavily", status=ServiceStatus.HEALTHY)):

        full = svc.get_full_health()
        assert full.overall_status == ServiceStatus.HEALTHY
        assert "operational" in full.summary.lower()
