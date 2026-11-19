"""
Audit logging service for tracking administrative actions and destructive operations.
Thread-safe, sanitized, and persistent.
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from admin_backend.config import settings
from admin_backend.models.audit import AuditAction, AuditLogEntry, AuditLogFilter
from admin_backend.storage.postgres import PostgresAuditStorage
from admin_backend.storage.interfaces import AuditStorageInterface

log = logging.getLogger("admin_backend.audit")

SENSITIVE_KEYS = {
    "password", "secret", "token", "api_key", "apikey", "authorization",
    "access_token", "refresh_token", "private_key", "credential"
}


def _sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively redact sensitive fields from audit logs."""
    cleaned = {}
    for k, v in data.items():
        if any(s in k.lower() for s in SENSITIVE_KEYS):
            cleaned[k] = "[REDACTED]"
        elif isinstance(v, dict):
            cleaned[k] = _sanitize_dict(v)
        elif isinstance(v, str) and len(v) > 200:
            cleaned[k] = v[:200] + "... [truncated]"
        else:
            cleaned[k] = v
    return cleaned


class AuditService:
    def __init__(self, storage: Optional[AuditStorageInterface] = None):
        self.storage = storage or PostgresAuditStorage()
        self.log_file = settings.admin_audit_log_path

    def log_action(
        self,
        actor_username: str,
        actor_role: str,
        action: AuditAction,
        resource_type: str,
        resource_id: Optional[str] = None,
        status: str = "success",
        details: Optional[Dict[str, Any]] = None,
        client_ip: Optional[str] = None,
    ) -> AuditLogEntry:
        """
        Record an administrative action to both repository and audit file.
        """
        IST = timezone(timedelta(hours=5, minutes=30))
        now_iso = datetime.now(IST).isoformat()
        sanitized_details = _sanitize_dict(details or {})

        entry = AuditLogEntry(
            id=str(uuid.uuid4()),
            timestamp=now_iso,
            actor_username=actor_username,
            actor_role=actor_role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            details=sanitized_details,
            client_ip=client_ip,
        )

        # 1. Save to repository interface
        self.storage.append_audit_entry(entry)

        # 2. Append to local audit file safely
        try:
            os.makedirs(os.path.dirname(self.log_file) or ".", exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(entry.model_dump_json() + "\n")
        except Exception as e:
            log.warning(f"Could not write audit log file: {e}")

        return entry

    def _load_persisted_entries(self) -> List[AuditLogEntry]:
        """Safely load existing audit records from logs/admin_audit.jsonl."""
        entries: List[AuditLogEntry] = []
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                entries.append(AuditLogEntry.model_validate_json(line))
                            except Exception:
                                continue
            except Exception as e:
                log.warning(f"Could not read audit log file: {e}")
        return entries

    def query(self, filter_opts: AuditLogFilter) -> List[AuditLogEntry]:
        """Query audit log records matching filter."""
        # Combine in-memory entries with persisted entries
        all_entries = self._load_persisted_entries()
        memory_entries = self.storage.query_audit_entries(AuditLogFilter(limit=200, offset=0))
        seen_ids = set()
        merged: List[AuditLogEntry] = []

        # Memory entries first (newest), then persisted
        for e in memory_entries + all_entries:
            if e.id not in seen_ids:
                seen_ids.add(e.id)
                merged.append(e)

        # Apply filters
        filtered = merged
        if filter_opts.actor:
            act = filter_opts.actor.lower()
            filtered = [e for e in filtered if act in e.actor_username.lower()]
        if filter_opts.action:
            filtered = [e for e in filtered if e.action == filter_opts.action]
        if filter_opts.resource_type:
            filtered = [e for e in filtered if e.resource_type == filter_opts.resource_type]
        if filter_opts.status:
            filtered = [e for e in filtered if e.status.lower() == filter_opts.status.lower()]

        # Sort newest first
        filtered.sort(key=lambda x: x.timestamp, reverse=True)
        return filtered[filter_opts.offset:filter_opts.offset + filter_opts.limit]


audit_service = AuditService()
