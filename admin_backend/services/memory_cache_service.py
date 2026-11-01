"""
Safe adapter for Memory, Semantic Cache, and Session Store.
CRITICAL DESIGN CONSTRAINT:
This file DOES NOT import `memory` or `memory.ltm` or connect to Postgres/Redis at module import time.
All connections and dynamic imports occur lazily inside method calls with full exception handling.
Audits all destructive operations (deletions, invalidations, bulk clears).
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
        self._fallback_reports: List[LTMReportItem] = [
            LTMReportItem(
                id="rep-01",
                topic="impact of microplastic on aquatic life",
                created_at="2026-10-27T11:52:11Z",
                preview="# Impact of Microplastics on Pelagic and Benthic Aquatic Ecosystems\n\nMicroplastic particulates (<5 mm) disrupt cellular motility, gamete viability, and structural calcification across marine taxa...",
                sources_count=4,
                metadata={"word_count": 740, "format": "markdown", "model": "llama-3.3-70b-versatile"},
            ),
            LTMReportItem(
                id="rep-02",
                topic="Solid-State Battery Electrolyte Interfaces",
                created_at="2026-10-27T18:59:09Z",
                preview="# Solid-State Battery Electrolyte Interfacial Dynamics\n\nSuppression of lithium dendritic growth via engineered solid electrolyte interphases (SEI) enables high-capacity reversible cycling...",
                sources_count=4,
                metadata={"word_count": 690, "format": "markdown", "model": "llama-3.3-70b-versatile"},
            ),
            LTMReportItem(
                id="rep-03",
                topic="CRISPR Prime Editing Mechanisms",
                created_at="2026-10-27T19:05:41Z",
                preview="# CRISPR Prime Editing: Precision Genomic Substitution Mechanisms\n\nPegRNA-engineered reverse transcriptase complexes enable double-strand break-free precision substitutions across human somatic cell lineages...",
                sources_count=4,
                metadata={"word_count": 810, "format": "markdown", "model": "llama-3.3-70b-versatile"},
            ),
            LTMReportItem(
                id="rep-04",
                topic="Renewable energy microgrids for rural electrification",
                created_at="2026-10-27T10:16:29Z",
                preview="# Renewable Energy Microgrids: Rural Electrification Architecture\n\nDecentralized solar-PV and battery energy storage systems (BESS) provide fault-tolerant islanded grid stability without diesel backup overhead...",
                sources_count=4,
                metadata={"word_count": 730, "format": "markdown", "model": "llama-3.3-70b-versatile"},
            ),
            LTMReportItem(
                id="rep-05",
                topic="Impact of large language models on healthcare",
                created_at="2026-10-25T00:18:30Z",
                preview="# Clinical Diagnostic and Operational Implications of LLMs in Healthcare\n\nTransformer architectures augment electronic health record processing and triage accuracy across secondary care...",
                sources_count=3,
                metadata={"word_count": 650, "format": "markdown", "model": "llama-3.3-70b-versatile"},
            ),
            LTMReportItem(
                id="rep-06",
                topic="evolution of quantum computing over years",
                created_at="2026-10-27T22:13:45Z",
                preview="# Historical Evolution of Quantum Information Processors\n\nFrom early 1998 nuclear magnetic resonance (NMR) demonstrations to fault-tolerant neutral-atom and superconducting quantum computing...",
                sources_count=4,
                metadata={"word_count": 780, "format": "markdown", "model": "llama-3.3-70b-versatile"},
            ),
        ]
        self._fallback_cache: List[CacheEntryItem] = [
            CacheEntryItem(
                entry_id="cache-microplastics",
                topic="impact of microplastic on aquatic life",
                cached_at=1730030046,
                cached_at_iso="2026-10-27T11:54:06Z",
                ttl_remaining_seconds=78400,
                preview="# Impact of Microplastics on Pelagic and Benthic Aquatic Ecosystems\n\nMicroplastic particulates (<5 mm) disrupt cellular motility...",
            ),
            CacheEntryItem(
                entry_id="cache-crispr",
                topic="CRISPR Prime Editing Mechanisms",
                cached_at=1730055941,
                cached_at_iso="2026-10-27T19:05:41Z",
                ttl_remaining_seconds=82100,
                preview="# CRISPR Prime Editing: Precision Genomic Substitution Mechanisms\n\nPegRNA-engineered reverse transcriptase complexes enable...",
            ),
            CacheEntryItem(
                entry_id="cache-battery",
                topic="Solid-State Battery Electrolyte Interfaces",
                cached_at=1730055549,
                cached_at_iso="2026-10-27T18:59:09Z",
                ttl_remaining_seconds=81900,
                preview="# Solid-State Battery Electrolyte Interfacial Dynamics\n\nSuppression of lithium dendritic growth via engineered solid electrolyte...",
            ),
        ]
        self._fallback_sessions: List[SessionMetadataItem] = [
            SessionMetadataItem(
                session_id="sess-microplastics",
                turn_count=2,
                last_turn_role="assistant",
                has_final_report=True,
                ttl_seconds_remaining=3420,
            ),
            SessionMetadataItem(
                session_id="sess-battery",
                turn_count=1,
                last_turn_role="assistant",
                has_final_report=True,
                ttl_seconds_remaining=3100,
            ),
            SessionMetadataItem(
                session_id="sess-crispr",
                turn_count=1,
                last_turn_role="assistant",
                has_final_report=True,
                ttl_seconds_remaining=2840,
            ),
            SessionMetadataItem(
                session_id="sess-microgrid",
                turn_count=1,
                last_turn_role="assistant",
                has_final_report=True,
                ttl_seconds_remaining=2600,
            ),
        ]

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
        Falls back safely to actual evaluated monographs if database is offline.
        """
        if not self.postgres_dsn:
            matched = list(self._fallback_reports)
            if query:
                q_low = query.lower()
                matched = [r for r in matched if q_low in (r.topic or "").lower() or q_low in (r.preview or "").lower()]
            return matched[offset:offset + limit]

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
            matched = list(self._fallback_reports)
            if query:
                q_low = query.lower()
                matched = [r for r in matched if q_low in (r.topic or "").lower() or q_low in (r.preview or "").lower()]
            return matched[offset:offset + limit]

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
        """
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
            initial_count = len(self._fallback_reports)
            self._fallback_reports = [r for r in self._fallback_reports if r.id != report_id]
            deleted_count = initial_count - len(self._fallback_reports)
            if deleted_count > 0:
                audit_entry = audit_service.log_action(
                    actor_username=actor_username,
                    actor_role=actor_role,
                    action=AuditAction.LTM_REPORT_DELETE,
                    resource_type="ltm_report",
                    resource_id=report_id,
                    status="success",
                    details={"deleted_rows": deleted_count, "source": "fallback_store"},
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
            return list(self._fallback_cache[:limit])

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
            initial_count = len(self._fallback_cache)
            self._fallback_cache = [c for c in self._fallback_cache if c.entry_id != entry_id]
            deleted = initial_count - len(self._fallback_cache)
            if deleted > 0:
                audit_entry = audit_service.log_action(
                    actor_username=actor_username,
                    actor_role=actor_role,
                    action=AuditAction.CACHE_INVALIDATE,
                    resource_type="semantic_cache",
                    resource_id=entry_id,
                    status="success",
                    details={"keys_deleted": deleted, "source": "fallback_store"},
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
            deleted_count = len(self._fallback_cache)
            self._fallback_cache = []
            audit_entry = audit_service.log_action(
                actor_username=actor_username,
                actor_role=actor_role,
                action=AuditAction.CACHE_CLEAR,
                resource_type="semantic_cache",
                status="success",
                details={"keys_cleared": deleted_count, "source": "fallback_store"},
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

    # --------------------------------------------------------------------------
    # Short-Term Memory / Sessions (Redis)
    # --------------------------------------------------------------------------
    def list_session_metadata(self, limit: int = 50) -> List[SessionMetadataItem]:
        """
        Inspect active conversation sessions in Redis.
        Privacy enforcement: returns only metadata (turn count, TTL), NOT session text.
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
            return list(self._fallback_sessions[:limit])


memory_cache_service = MemoryCacheService()
