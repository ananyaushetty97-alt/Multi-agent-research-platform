"""
End-to-end route tests using FastAPI TestClient.
Tests authentication rejection (401), authorization role rejection (403),
successful admin access (200), and destructive confirmation guards (400).
"""
from unittest.mock import MagicMock, patch
from admin_backend.models.health import ServiceStatus


def test_unauthenticated_request_rejected(client):
    """Endpoints must reject requests missing bearer tokens with 401."""
    resp = client.get("/admin/health")
    assert resp.status_code == 401


def test_regular_user_rejected_from_admin_route(client, user_token):
    """Endpoints must reject non-admin users with 403 Forbidden."""
    headers = {"Authorization": f"Bearer {user_token}"}
    resp = client.get("/admin/health", headers=headers)
    assert resp.status_code == 403
    assert "Admin privileges required" in resp.json()["detail"]


def test_admin_access_allowed(client, admin_token):
    """Admin token should access protected endpoints."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Mock health checks so test runs fast and offline
    with patch("admin_backend.services.health_service.health_service.get_full_health") as mock_health:
        from admin_backend.models.health import DetailedSystemHealth, ProcessHealthInfo
        mock_health.return_value = DetailedSystemHealth(
            overall_status=ServiceStatus.HEALTHY,
            timestamp="2026-10-27T00:00:00Z",
            process=ProcessHealthInfo(pid=1234, python_version="3.11", uptime_seconds=10.0, platform="Test"),
            dependencies={},
            summary="All healthy",
        )
        resp = client.get("/admin/health", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["overall_status"] == "healthy"


def test_destructive_action_guard_without_confirmation(client, admin_token):
    """Destructive operations must fail with 400 when confirm is not provided."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.delete("/admin/memory/cache/test-entry", headers=headers)
    assert resp.status_code == 400
    assert "Destructive operation blocked" in resp.json()["detail"]


def test_destructive_action_guard_with_query_param(client, admin_token):
    """Destructive operation proceeds when confirm=true is supplied."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    with patch("admin_backend.services.memory_cache_service.memory_cache_service.invalidate_cache_entry") as mock_inval:
        from admin_backend.models.memory_cache import DestructiveActionResult
        mock_inval.return_value = DestructiveActionResult(
            action="invalidate_cache_entry",
            target_id="test-entry",
            affected_count=1,
            status="completed",
            message="Invalidated",
            audit_event_id="audit-123",
        )
        resp = client.delete("/admin/memory/cache/test-entry?confirm=true", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"


def test_destructive_action_guard_with_header(client, admin_token):
    """Destructive operation proceeds when X-Confirm-Destructive header is supplied."""
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "X-Confirm-Destructive": "true",
    }
    with patch("admin_backend.services.memory_cache_service.memory_cache_service.clear_all_cache") as mock_clear:
        from admin_backend.models.memory_cache import DestructiveActionResult
        mock_clear.return_value = DestructiveActionResult(
            action="clear_all_cache",
            target_id="all",
            affected_count=5,
            status="completed",
            message="Cache cleared",
            audit_event_id="audit-456",
        )
        resp = client.post("/admin/memory/cache/clear", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"


def test_export_scores_csv(client, admin_token):
    """Exporting scores returns text/csv attachment."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    with patch("admin_backend.services.export_service.export_service.export_scores_to_csv", return_value="id,topic\n1,AI"):
        resp = client.get("/admin/export/scores/csv", headers=headers)
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "id,topic" in resp.text


def test_redteam_routes_require_admin(client, user_token):
    headers = {"Authorization": f"Bearer {user_token}"}
    resp = client.get("/admin/safety/redteam", headers=headers)
    assert resp.status_code == 403

    resp = client.post("/admin/safety/redteam/run", headers=headers)
    assert resp.status_code == 403


def test_admin_can_trigger_live_redteam(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    with patch("admin_backend.routes.safety_routes.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        with patch("admin_backend.routes.safety_routes.safety_service.load_redteam_summary") as mock_load:
            from admin_backend.models.safety import RedTeamRunSummary
            mock_load.return_value = RedTeamRunSummary(
                run_id="redteam-test",
                recorded_at="2026-11-23T10:00:00+00:00",
                source_file="logs/redteam_results.json",
                mode="live-pyrit",
                defense_enabled=True,
                total_attacks=11,
                attacks_defended=11,
                attacks_reached_user=0,
                defense_rate_pct=100.0,
                indirect_count=6,
                direct_count=5,
            )
            resp = client.post("/admin/safety/redteam/run", headers=headers)
            command = mock_run.call_args.args[0]

    assert resp.status_code == 200
    assert resp.json()["mode"] == "live-pyrit"
    assert "--all" in command
    assert "--fake-llm" not in command
