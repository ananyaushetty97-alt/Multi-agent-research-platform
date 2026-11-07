"""
Safe adapter for Memory, Semantic Cache, and Session Store.
CRITICAL DESIGN CONSTRAINT:
This file DOES NOT import `memory` or `memory.ltm` or connect to Postgres/Redis at module import time.
All connections and dynamic imports occur lazily inside method calls with full exception handling.
Audits all destructive operations (deletions, invalidations, bulk clears).
Only returns REAL data from Redis/PostgreSQL - no fallback/fake data.
"""
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from admin_backend.config import settings
from admin_backend.models.audit import AuditAction
from admin_backend.models.memory_cache import (
    CacheEntryItem,
    DestructiveActionResult,
    LTMReportItem,
    SessionMetadataItem,
)
from admin_backend.services.audit_service import audit_service

log = logging.getLogger("admin_backend.memory_cache")


class MemoryCacheService:
    def __init__(self):
        self.redis_url = settings.redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.postgres_dsn = settings.postgres_dsn or os.environ.get("POSTGRES_DSN", "")

    # --------------------------------------------------------------------------
    # Long-Term Memory (Postgres + pgvector)
    # --------------------------------------------------------------------------
    def list_ltm_reports(
        self,
        query: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[LTMReportItem]:
        """
        List or search reports stored in PostgreSQL long-term memory.
        Uses raw SQL via psycopg without triggering memory module initialization side-effects.
        Returns empty list if database is not configured or offline - NO fallback data.
        """
        if not self.postgres_dsn:
            log.warning("PostgreSQL DSN not configured - returning empty LTM report list")
            return []

        try:
            import psycopg
            from psycopg.rows import dict_row

            sql = "SELECT id, text, metadata, created_at FROM reports "
            params: List[Any] = []

            if query:
                sql += "WHERE text ILIKE %s OR metadata::text ILIKE %s "
                pattern = f"%{query}%"
                params.extend([pattern, pattern])

            sql += "ORDER BY created_at DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])

            with psycopg.connect(self.postgres_dsn, row_factory=dict_row, connect_timeout=2) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    rows = cur.fetchall()

            results = []
            for r in rows:
                meta = r.get("metadata") or {}
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except Exception:
                        meta = {}

                text = r.get("text", "")
                preview = text[:160] + ("..." if len(text) > 160 else "")
                sources = meta.get("sources") or []

                created_at = r.get("created_at")
                created_iso = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at)

                results.append(
                    LTMReportItem(
                        id=str(r["id"]),
                        topic=meta.get("topic"),
                        created_at=created_iso,
                        preview=preview,
                        sources_count=len(sources),
                        metadata=meta,
                    )
                )
            return results
        except Exception as e:
            log.warning(f"Failed to query LTM reports from database: {e}")
            return []

    def delete_ltm_report(
        self,
        report_id: str,
        actor_username: str = "admin",
        actor_role: str = "admin",
        client_ip: Optional[str] = None,
    ) -> DestructiveActionResult:
        """
        Delete a report from PostgreSQL long-term memory.
        Enforces audit logging.
        Returns error if database is not configured or operation fails - NO fallback.
        """
        if not self.postgres_dsn:
            raise RuntimeError("PostgreSQL DSN not configured - cannot delete LTM report")

        try:
            import psycopg
            with psycopg.connect(self.postgres_dsn, connect_timeout=2) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM reports WHERE id = %s", (report_id,))
                    deleted_count = cur.rowcount
                conn.commit()

            audit_entry = audit_service.log_action(
                actor_username=actor_username,
                actor_role=actor_role,
                action=AuditAction.LTM_REPORT_DELETE,
                resource_type="ltm_report",
                resource_id=report_id,
                status="success",
                details={"deleted_rows": deleted_count},
                client_ip=client_ip,
            )

            return DestructiveActionResult(
                action="delete_ltm_report",
                target_id=report_id,
                affected_count=deleted_count,
                status="completed",
                message=f"Report {report_id} successfully deleted from long-term memory",
                audit_event_id=audit_entry.id,
            )
        except Exception as e:
            audit_service.log_action(
                actor_username=actor_username,
                actor_role=actor_role,
                action=AuditAction.LTM_REPORT_DELETE,
                resource_type="ltm_report",
                resource_id=report_id,
                status="failure",
                details={"error": str(e)},
                client_ip=client_ip,
            )
            raise RuntimeError(f"Failed to delete LTM report: {e}")

    # --------------------------------------------------------------------------
    # Semantic Cache (Redis)
    # --------------------------------------------------------------------------
    def list_cache_entries(self, limit: int = 50) -> List[CacheEntryItem]:
        """
        Scan semantic cache entries in Redis without loading the memory module.
        Returns empty list if Redis is not available - NO fallback data.
        """
        try:
            import redis
            client = redis.Redis.from_url(self.redis_url, decode_responses=True, socket_timeout=1.5)
            entries: List[CacheEntryItem] = []

            for key in client.scan_iter(match="semcache:*", count=100):
                if len(entries) >= limit:
                    break
                raw = client.get(key)
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                    ttl = client.ttl(key)
                    report_obj = data.get("report")
                    if isinstance(report_obj, dict):
                        preview_src = report_obj.get("report") or report_obj.get("summary") or str(report_obj)
                    else:
                        preview_src = str(report_obj or "")

                    preview = preview_src[:160] + ("..." if len(preview_src) > 160 else "")
                    cached_at = data.get("cached_at")
                    cached_at_iso = (
                        datetime.fromtimestamp(cached_at, tz=timezone.utc).isoformat()
                        if cached_at else None
                    )

                    entries.append(
                        CacheEntryItem(
                            entry_id=str(data.get("id") or key.replace("semcache:", "")),
                            topic=str(data.get("topic", "")),
                            cached_at=cached_at,
                            cached_at_iso=cached_at_iso,
                            ttl_remaining_seconds=ttl if ttl >= 0 else None,
                            preview=preview,
                        )
                    )
                except Exception:
                    continue

            return entries
        except Exception as e:
            log.warning(f"Failed to scan semantic cache in Redis: {e}")
            return []

    def invalidate_cache_entry(
        self,
        entry_id: str,
        actor_username: str = "admin",
        actor_role: str = "admin",
        client_ip: Optional[str] = None,
    ) -> DestructiveActionResult:
        """
        Remove a specific semantic cache key.
        Enforces audit logging.
        Raises error if Redis is not available - NO fallback data.
        """
        try:
            import redis
            client = redis.Redis.from_url(self.redis_url, decode_responses=True, socket_timeout=1.5)
            redis_key = f"semcache:{entry_id}"
            deleted = client.delete(redis_key)

            audit_entry = audit_service.log_action(
                actor_username=actor_username,
                actor_role=actor_role,
                action=AuditAction.CACHE_INVALIDATE,
                resource_type="semantic_cache",
                resource_id=entry_id,
                status="success" if deleted > 0 else "noop",
                details={"keys_deleted": deleted},
                client_ip=client_ip,
            )

            return DestructiveActionResult(
                action="invalidate_cache_entry",
                target_id=entry_id,
                affected_count=deleted,
                status="completed",
                message=f"Cache entry {entry_id} invalidated ({deleted} key removed)",
                audit_event_id=audit_entry.id,
            )
        except Exception as e:
            audit_service.log_action(
                actor_username=actor_username,
                actor_role=actor_role,
                action=AuditAction.CACHE_INVALIDATE,
                resource_type="semantic_cache",
                resource_id=entry_id,
                status="failure",
                details={"error": str(e)},
                client_ip=client_ip,
            )
            raise RuntimeError(f"Failed to invalidate cache entry: {e}")

    def clear_all_cache(
        self,
        actor_username: str = "admin",
        actor_role: str = "admin",
        client_ip: Optional[str] = None,
    ) -> DestructiveActionResult:
        """
        Clear all semantic cache entries.
        Enforces audit logging.
        Raises error if Redis is not available - NO fallback data.
        """
        try:
            import redis
            client = redis.Redis.from_url(self.redis_url, decode_responses=True, socket_timeout=1.5)
            deleted_count = 0
            keys_to_delete = list(client.scan_iter(match="semcache:*", count=200))
            if keys_to_delete:
                deleted_count = client.delete(*keys_to_delete)

            audit_entry = audit_service.log_action(
                actor_username=actor_username,
                actor_role=actor_role,
                action=AuditAction.CACHE_CLEAR,
                resource_type="semantic_cache",
                status="success",
                details={"keys_cleared": deleted_count},
                client_ip=client_ip,
            )

            return DestructiveActionResult(
                action="clear_all_cache",
                target_id="all",
                affected_count=deleted_count,
                status="completed",
                message=f"Semantic cache completely wiped: {deleted_count} entries removed",
                audit_event_id=audit_entry.id,
            )
        except Exception as e:
            audit_service.log_action(
                actor_username=actor_username,
                actor_role=actor_role,
                action=AuditAction.CACHE_CLEAR,
                resource_type="semantic_cache",
                status="failure",
                details={"error": str(e)},
                client_ip=client_ip,
            )
            raise RuntimeError(f"Failed to clear all cache: {e}")

    # --------------------------------------------------------------------------
    # Short-Term Memory / Sessions (Redis)
    # --------------------------------------------------------------------------
    def list_session_metadata(self, limit: int = 50) -> List[SessionMetadataItem]:
        """
        Inspect active conversation sessions in Redis.
        Privacy enforcement: returns only metadata (turn count, TTL), NOT session text.
        Returns empty list if Redis is not available - NO fallback data.
        """
        try:
            import redis
            client = redis.Redis.from_url(self.redis_url, decode_responses=True, socket_timeout=1.5)
            sessions: List[SessionMetadataItem] = []

            for key in client.scan_iter(match="session:*", count=100):
                if len(sessions) >= limit:
                    break
                session_id = key.replace("session:", "")
                ttl = client.ttl(key)
                raw = client.get(key)
                turn_count = 0
                last_role = None
                has_report = False

                if raw:
                    try:
                        data = json.loads(raw)
                        history = data.get("history", [])
                        turn_count = len(history)
                        if history:
                            last_role = history[-1].get("role")
                        has_report = bool(data.get("last_report")) or any(
                            h.get("role") == "report" for h in history
                        )
                    except Exception:
                        pass

                sessions.append(
                    SessionMetadataItem(
                        session_id=session_id,
                        turn_count=turn_count,
                        last_turn_role=last_role,
                        has_final_report=has_report,
                        ttl_seconds_remaining=ttl if ttl >= 0 else None,
                    )
                )
            return sessions
        except Exception as e:
            log.warning(f"Failed to scan sessions in Redis: {e}")
            return []


memory_cache_service = MemoryCacheService()
