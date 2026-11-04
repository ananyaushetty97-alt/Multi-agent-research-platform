"""
Unit tests for memory, cache, and session management adapter.
Uses mocks to test Redis and PostgreSQL operations without requiring active databases.
"""
import json
from unittest.mock import MagicMock, patch

from admin_backend.models.audit import AuditAction
from admin_backend.services.memory_cache_service import MemoryCacheService
from admin_backend.services.audit_service import audit_service


def test_list_cache_entries_mocked():
    svc = MemoryCacheService()

    mock_redis = MagicMock()
    mock_redis.scan_iter.return_value = ["semcache:item-1", "semcache:item-2"]
    mock_redis.get.side_effect = lambda k: json.dumps({
        "id": k.replace("semcache:", ""),
        "topic": "Renewable microgrids",
        "cached_at": 1700000000.0,
        "report": {"report": "Detailed microgrids report text."}
    })
    mock_redis.ttl.return_value = 3600

    with patch("redis.Redis.from_url", return_value=mock_redis):
        entries = svc.list_cache_entries(limit=10)
        assert len(entries) == 2
        assert entries[0].entry_id == "item-1"
        assert entries[0].topic == "Renewable microgrids"
        assert entries[0].ttl_remaining_seconds == 3600


def test_invalidate_cache_entry_audited():
    svc = MemoryCacheService()
    mock_redis = MagicMock()
    mock_redis.delete.return_value = 1

    with patch("redis.Redis.from_url", return_value=mock_redis):
        res = svc.invalidate_cache_entry(
            entry_id="entry-to-remove",
            actor_username="admin_alice",
            actor_role="admin",
            client_ip="192.168.1.100",
        )

        assert res.status == "completed"
        assert res.affected_count == 1
        assert res.audit_event_id is not None

        # Verify audit log recorded this
        from admin_backend.models.audit import AuditLogFilter
        logs = audit_service.query(AuditLogFilter(action=AuditAction.CACHE_INVALIDATE))
        assert any(l.resource_id == "entry-to-remove" for l in logs)


def test_clear_all_cache_audited():
    svc = MemoryCacheService()
    mock_redis = MagicMock()
    mock_redis.scan_iter.return_value = ["semcache:1", "semcache:2"]
    mock_redis.delete.return_value = 2

    with patch("redis.Redis.from_url", return_value=mock_redis):
        res = svc.clear_all_cache(
            actor_username="admin_alice",
            actor_role="admin",
        )

        assert res.status == "completed"
        assert res.affected_count == 2


def test_session_metadata_privacy():
    svc = MemoryCacheService()
    mock_redis = MagicMock()
    mock_redis.scan_iter.return_value = ["session:sess-100"]
    mock_redis.ttl.return_value = 1800
    mock_redis.get.return_value = json.dumps({
        "history": [
            {"role": "user", "content": "Sensitive medical question"},
            {"role": "report", "content": "Sensitive medical answer text"}
        ],
        "last_report": {"role": "report", "content": "Sensitive medical answer text"}
    })

    with patch("redis.Redis.from_url", return_value=mock_redis):
        sessions = svc.list_session_metadata()
        assert len(sessions) == 1
        assert sessions[0].session_id == "sess-100"
        assert sessions[0].turn_count == 2
        assert sessions[0].last_turn_role == "report"
        assert sessions[0].has_final_report is True
        # Ensure session contents are not leaked in the metadata object
        assert not hasattr(sessions[0], "history")
        assert not hasattr(sessions[0], "content")
