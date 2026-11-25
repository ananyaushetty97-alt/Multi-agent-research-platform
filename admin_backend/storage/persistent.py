"""
Persistent JSONL file-based storage implementations.
Data persists across server restarts using append-only JSONL files.
"""
import json
import logging
import os
import threading
from typing import Optional, List, Dict, Any

from admin_backend.models.audit import (
    AuditLogEntry, AuditLogFilter,
    UserActivityLogEntry, UserActivityLogFilter
)
from admin_backend.models.traces import RequestTrace, TraceFilter
from admin_backend.models.safety import SafetyEvent, SafetyEventFilter
from admin_backend.models.metrics import RequestMetric
from admin_backend.storage.interfaces import (
    UserStorageInterface,
    AuditStorageInterface,
    TraceStorageInterface,
    SafetyStorageInterface,
    MetricStorageInterface,
)
from admin_backend.config import settings

log = logging.getLogger("admin_backend.storage.persistent")


class PersistentTraceStorage(TraceStorageInterface):
    """Thread-safe trace storage with JSONL file persistence."""

    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path or settings.admin_traces_log_path
        self._traces_by_id: Dict[str, RequestTrace] = {}
        self._order: List[str] = []
        self._lock = threading.Lock()
        self._load_persisted()

    def _load_persisted(self) -> None:
        """Load existing traces from JSONL file."""
        if not os.path.exists(self.file_path):
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        trace = RequestTrace.model_validate(data)
                        self._traces_by_id[trace.request_id] = trace
                        if trace.request_id not in self._order:
                            self._order.append(trace.request_id)
                    except Exception:
                        continue
            log.info(f"Loaded {len(self._traces_by_id)} traces from {self.file_path}")
        except Exception as e:
            log.warning(f"Could not load traces from {self.file_path}: {e}")

    def _append_to_file(self, trace: RequestTrace) -> None:
        """Append a trace to the JSONL file."""
        try:
            os.makedirs(os.path.dirname(self.file_path) or ".", exist_ok=True)
            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(trace.model_dump_json() + "\n")
        except Exception as e:
            log.warning(f"Could not write trace to {self.file_path}: {e}")

    def save_trace(self, trace: RequestTrace) -> None:
        with self._lock:
            if trace.request_id not in self._traces_by_id:
                self._order.append(trace.request_id)
            self._traces_by_id[trace.request_id] = trace
            self._append_to_file(trace)

    def get_trace(self, request_id: str) -> Optional[RequestTrace]:
        with self._lock:
            return self._traces_by_id.get(request_id)

    def query_traces(self, filter_opts: TraceFilter) -> List[RequestTrace]:
        with self._lock:
            all_traces = [self._traces_by_id[rid] for rid in reversed(self._order) if rid in self._traces_by_id]

        res = all_traces
        if filter_opts.session_id:
            res = [t for t in res if t.session_id == filter_opts.session_id]
        if filter_opts.intent:
            res = [t for t in res if t.intent == filter_opts.intent]
        if filter_opts.outcome:
            res = [t for t in res if t.outcome == filter_opts.outcome]
        if filter_opts.min_duration_ms is not None:
            res = [t for t in res if (t.duration_ms or 0) >= filter_opts.min_duration_ms]
        if filter_opts.error_category:
            res = [t for t in res if t.error_category == filter_opts.error_category]

        start = filter_opts.offset
        end = start + filter_opts.limit
        return res[start:end]

    def clear(self):
        with self._lock:
            self._traces_by_id.clear()
            self._order.clear()


class PersistentSafetyStorage(SafetyStorageInterface):
    """Thread-safe safety event storage with JSONL file persistence."""

    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path or settings.admin_safety_log_path
        self._events: List[SafetyEvent] = []
        self._lock = threading.Lock()
        self._load_persisted()

    def _load_persisted(self) -> None:
        """Load existing safety events from JSONL file."""
        if not os.path.exists(self.file_path):
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        event = SafetyEvent.model_validate(data)
                        self._events.append(event)
                    except Exception:
                        continue
            log.info(f"Loaded {len(self._events)} safety events from {self.file_path}")
        except Exception as e:
            log.warning(f"Could not load safety events from {self.file_path}: {e}")

    def _append_to_file(self, event: SafetyEvent) -> None:
        """Append a safety event to the JSONL file."""
        try:
            os.makedirs(os.path.dirname(self.file_path) or ".", exist_ok=True)
            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(event.model_dump_json() + "\n")
        except Exception as e:
            log.warning(f"Could not write safety event to {self.file_path}: {e}")

    def record_safety_event(self, event: SafetyEvent) -> None:
        with self._lock:
            self._events.append(event)
            self._append_to_file(event)

    def query_safety_events(self, filter_opts: SafetyEventFilter) -> List[SafetyEvent]:
        with self._lock:
            matched = list(self._events)

        if filter_opts.check_type:
            matched = [e for e in matched if e.check_type == filter_opts.check_type]
        if filter_opts.outcome:
            matched = [e for e in matched if e.outcome == filter_opts.outcome]
        if filter_opts.source:
            matched = [e for e in matched if e.source == filter_opts.source]

        # Newest first
        matched = list(reversed(matched))
        start = filter_opts.offset
        end = start + filter_opts.limit
        return matched[start:end]

    def clear(self):
        with self._lock:
            self._events.clear()


class PersistentAuditStorage(AuditStorageInterface):
    """Thread-safe audit storage with JSONL file persistence for both audit and user activity logs."""

    def __init__(self, audit_file_path: Optional[str] = None, activity_file_path: Optional[str] = None):
        from admin_backend.config import settings
        self.audit_file_path = audit_file_path or settings.admin_audit_log_path
        self.activity_file_path = activity_file_path or settings.admin_user_activity_log_path
        self._entries: List[AuditLogEntry] = []
        self._user_activity_entries: List[UserActivityLogEntry] = []
        self._lock = threading.Lock()
        self._load_persisted()

    def _load_persisted(self) -> None:
        """Load existing audit and user activity entries from JSONL files."""
        # Load audit entries
        if os.path.exists(self.audit_file_path):
            try:
                with open(self.audit_file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            entry = AuditLogEntry.model_validate(data)
                            self._entries.append(entry)
                        except Exception:
                            continue
                log.info(f"Loaded {len(self._entries)} audit entries from {self.audit_file_path}")
            except Exception as e:
                log.warning(f"Could not load audit entries from {self.audit_file_path}: {e}")

        # Load user activity entries
        if os.path.exists(self.activity_file_path):
            try:
                with open(self.activity_file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            entry = UserActivityLogEntry.model_validate(data)
                            self._user_activity_entries.append(entry)
                        except Exception:
                            continue
                log.info(f"Loaded {len(self._user_activity_entries)} user activity entries from {self.activity_file_path}")
            except Exception as e:
                log.warning(f"Could not load user activity entries from {self.activity_file_path}: {e}")

    def _append_audit_to_file(self, entry: AuditLogEntry) -> None:
        """Append an audit entry to the JSONL file."""
        try:
            os.makedirs(os.path.dirname(self.audit_file_path) or ".", exist_ok=True)
            with open(self.audit_file_path, "a", encoding="utf-8") as f:
                f.write(entry.model_dump_json() + "\n")
        except Exception as e:
            log.warning(f"Could not write audit entry to {self.audit_file_path}: {e}")

    def _append_activity_to_file(self, entry: UserActivityLogEntry) -> None:
        """Append a user activity entry to the JSONL file."""
        try:
            os.makedirs(os.path.dirname(self.activity_file_path) or ".", exist_ok=True)
            with open(self.activity_file_path, "a", encoding="utf-8") as f:
                f.write(entry.model_dump_json() + "\n")
        except Exception as e:
            log.warning(f"Could not write user activity entry to {self.activity_file_path}: {e}")

    def append_audit_entry(self, entry: AuditLogEntry) -> None:
        with self._lock:
            self._entries.append(entry)
            self._append_audit_to_file(entry)

    def query_audit_entries(self, filter_opts: AuditLogFilter) -> List[AuditLogEntry]:
        with self._lock:
            matched = list(self._entries)

        if filter_opts.actor:
            matched = [e for e in matched if e.actor_username.lower() == filter_opts.actor.lower()]
        if filter_opts.action:
            matched = [e for e in matched if e.action == filter_opts.action]
        if filter_opts.resource_type:
            matched = [e for e in matched if e.resource_type == filter_opts.resource_type]
        if filter_opts.status:
            matched = [e for e in matched if e.status == filter_opts.status]

        # Newest first
        matched = list(reversed(matched))
        start = filter_opts.offset
        end = start + filter_opts.limit
        return matched[start:end]

    def append_user_activity_entry(self, entry: UserActivityLogEntry) -> None:
        with self._lock:
            self._user_activity_entries.append(entry)
            self._append_activity_to_file(entry)

    def query_user_activity_entries(self, filter_opts: UserActivityLogFilter) -> List[UserActivityLogEntry]:
        with self._lock:
            matched = list(self._user_activity_entries)

        if filter_opts.username:
            matched = [e for e in matched if e.username.lower() == filter_opts.username.lower()]
        if filter_opts.action:
            matched = [e for e in matched if e.action == filter_opts.action]
        if filter_opts.status:
            matched = [e for e in matched if e.status == filter_opts.status]
        if filter_opts.session_id:
            matched = [e for e in matched if e.session_id == filter_opts.session_id]
        if filter_opts.start_date:
            matched = [e for e in matched if e.timestamp >= filter_opts.start_date]
        if filter_opts.end_date:
            matched = [e for e in matched if e.timestamp <= filter_opts.end_date]

        # Newest first
        matched = list(reversed(matched))
        start = filter_opts.offset
        end = start + filter_opts.limit
        return matched[start:end]

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._user_activity_entries.clear()


class PersistentMetricStorage(MetricStorageInterface):
    """Thread-safe metric storage with JSONL file persistence."""

    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path or settings.admin_metrics_log_path
        self._metrics: List[RequestMetric] = []
        self._lock = threading.Lock()
        self._load_persisted()

    def _load_persisted(self) -> None:
        """Load existing metrics from JSONL file."""
        if not os.path.exists(self.file_path):
            return
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        metric = RequestMetric.model_validate(data)
                        self._metrics.append(metric)
                    except Exception:
                        continue
            log.info(f"Loaded {len(self._metrics)} metrics from {self.file_path}")
        except Exception as e:
            log.warning(f"Could not load metrics from {self.file_path}: {e}")

    def _append_to_file(self, metric: RequestMetric) -> None:
        """Append a metric to the JSONL file."""
        try:
            os.makedirs(os.path.dirname(self.file_path) or ".", exist_ok=True)
            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(metric.model_dump_json() + "\n")
        except Exception as e:
            log.warning(f"Could not write metric to {self.file_path}: {e}")

    def record_metric(self, metric: RequestMetric) -> None:
        with self._lock:
            self._metrics.append(metric)
            self._append_to_file(metric)

    def query_metrics(self, since_iso: Optional[str] = None) -> List[RequestMetric]:
        with self._lock:
            if not since_iso:
                return list(self._metrics)
            return [m for m in self._metrics if m.timestamp >= since_iso]

    def clear(self):
        with self._lock:
            self._metrics.clear()