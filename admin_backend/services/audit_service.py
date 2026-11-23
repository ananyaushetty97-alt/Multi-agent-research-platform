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
from admin_backend.models.audit import (
    AuditAction, AuditLogEntry, AuditLogFilter,
    UserActivityAction, UserActivityLogEntry, UserActivityLogFilter
)
from admin_backend.storage.persistent import PersistentAuditStorage
from admin_backend.storage.interfaces import AuditStorageInterface
from uuid import UUID

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
        self.storage = storage or PersistentAuditStorage()
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

        # Convert UUID to string if needed
        if isinstance(resource_id, UUID):
            resource_id = str(resource_id)

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

        # Save to repository interface (handles file persistence)
        self.storage.append_audit_entry(entry)

        return entry

    def log_user_activity(
        self,
        session_id: str,
        username: str,
        action: UserActivityAction,
        status: str = "success",
        topic: Optional[str] = None,
        email: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        actor_role: str = "user",
    ) -> UserActivityLogEntry:
        """
        Record a user activity action (research query, login, etc.).
        """
        IST = timezone(timedelta(hours=5, minutes=30))
        now_iso = datetime.now(IST).isoformat()
        sanitized_details = _sanitize_dict(details or {})

        entry = UserActivityLogEntry(
            id=str(uuid.uuid4()),
            timestamp=now_iso,
            session_id=session_id,
            username=username,
            email=email,
            action=action,
            topic=topic,
            status=status,
            details=sanitized_details,
            client_ip=client_ip,
            user_agent=user_agent,
            actor_role=actor_role,
        )

        # Save to repository
        self.storage.append_user_activity_entry(entry)

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
        """Query admin audit log records matching filter."""
        return self.storage.query_audit_entries(filter_opts)

    def query_user_activity(self, filter_opts: UserActivityLogFilter) -> List[UserActivityLogEntry]:
        """Query user activity log records matching filter."""
        return self.storage.query_user_activity_entries(filter_opts)


audit_service = AuditService()
