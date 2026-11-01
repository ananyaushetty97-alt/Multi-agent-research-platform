"""
In-memory, thread-safe repository implementations.
Allows the admin module to be tested and reviewed completely standalone
without requiring live PostgreSQL or Redis databases.
"""
import threading
from typing import Optional, List, Dict, Any

from admin_backend.models.audit import AuditLogEntry, AuditLogFilter
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


class InMemoryUserStorage(UserStorageInterface):
    def __init__(self):
        self._users_by_id: Dict[str, Dict[str, Any]] = {}
        self._users_by_name: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._users_by_name.get(username.lower())

    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._users_by_id.get(user_id)

    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            uid = user_data["id"]
            uname = user_data["username"].lower()
            record = dict(user_data)
            self._users_by_id[uid] = record
            self._users_by_name[uname] = record
            return record

    def clear(self):
        with self._lock:
            self._users_by_id.clear()
            self._users_by_name.clear()


class InMemoryAuditStorage(AuditStorageInterface):
    def __init__(self):
        self._entries: List[AuditLogEntry] = []
        self._lock = threading.Lock()

    def append_audit_entry(self, entry: AuditLogEntry) -> None:
        with self._lock:
            self._entries.append(entry)

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

    def clear(self):
        with self._lock:
            self._entries.clear()


class InMemoryTraceStorage(TraceStorageInterface):
    def __init__(self):
        self._traces_by_id: Dict[str, RequestTrace] = {}
        self._order: List[str] = []
        self._lock = threading.Lock()

    def save_trace(self, trace: RequestTrace) -> None:
        with self._lock:
            if trace.request_id not in self._traces_by_id:
                self._order.append(trace.request_id)
            self._traces_by_id[trace.request_id] = trace

    def get_trace(self, request_id: str) -> Optional[RequestTrace]:
        with self._lock:
            return self._traces_by_id.get(request_id)

    def query_traces(self, filter_opts: TraceFilter) -> List[RequestTrace]:
        with self._lock:
            all_traces = [self._traces_by_id[rid] for rid in reversed(self._order)]

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


class InMemorySafetyStorage(SafetyStorageInterface):
    def __init__(self):
        self._events: List[SafetyEvent] = []
        self._lock = threading.Lock()

    def record_safety_event(self, event: SafetyEvent) -> None:
        with self._lock:
            self._events.append(event)

    def query_safety_events(self, filter_opts: SafetyEventFilter) -> List[SafetyEvent]:
        with self._lock:
            matched = list(self._events)

        if filter_opts.check_type:
            matched = [e for e in matched if e.check_type == filter_opts.check_type]
        if filter_opts.outcome:
            matched = [e for e in matched if e.outcome == filter_opts.outcome]

        # Newest first
        matched = list(reversed(matched))
        start = filter_opts.offset
        end = start + filter_opts.limit
        return matched[start:end]

    def clear(self):
        with self._lock:
            self._events.clear()


class InMemoryMetricStorage(MetricStorageInterface):
    def __init__(self):
        self._metrics: List[RequestMetric] = []
        self._lock = threading.Lock()

    def record_metric(self, metric: RequestMetric) -> None:
        with self._lock:
            self._metrics.append(metric)

    def query_metrics(self, since_iso: Optional[str] = None) -> List[RequestMetric]:
        with self._lock:
            if not since_iso:
                return list(self._metrics)
            return [m for m in self._metrics if m.timestamp >= since_iso]

    def clear(self):
        with self._lock:
            self._metrics.clear()
