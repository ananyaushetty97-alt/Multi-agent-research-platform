"""
Abstract storage repository interfaces.
Keeps data access decoupled from concrete databases, allowing isolated review,
mocking in unit tests, and safe future PostgreSQL integration.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

from admin_backend.models.audit import AuditLogEntry, AuditLogFilter
from admin_backend.models.traces import RequestTrace, TraceFilter
from admin_backend.models.safety import SafetyEvent, SafetyEventFilter
from admin_backend.models.metrics import RequestMetric


class UserStorageInterface(ABC):
    @abstractmethod
    def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Retrieve user by username."""
        pass

    @abstractmethod
    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve user by user ID."""
        pass

    @abstractmethod
    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Store a new user."""
        pass


class AuditStorageInterface(ABC):
    @abstractmethod
    def append_audit_entry(self, entry: AuditLogEntry) -> None:
        """Append an audit log record."""
        pass

    @abstractmethod
    def query_audit_entries(self, filter_opts: AuditLogFilter) -> List[AuditLogEntry]:
        """Query audit log records matching criteria."""
        pass


class TraceStorageInterface(ABC):
    @abstractmethod
    def save_trace(self, trace: RequestTrace) -> None:
        """Store a request trace."""
        pass

    @abstractmethod
    def get_trace(self, request_id: str) -> Optional[RequestTrace]:
        """Get trace by request ID."""
        pass

    @abstractmethod
    def query_traces(self, filter_opts: TraceFilter) -> List[RequestTrace]:
        """Query request traces matching criteria."""
        pass


class SafetyStorageInterface(ABC):
    @abstractmethod
    def record_safety_event(self, event: SafetyEvent) -> None:
        """Record a safety or blocked event."""
        pass

    @abstractmethod
    def query_safety_events(self, filter_opts: SafetyEventFilter) -> List[SafetyEvent]:
        """Query safety events matching criteria."""
        pass


class MetricStorageInterface(ABC):
    @abstractmethod
    def record_metric(self, metric: RequestMetric) -> None:
        """Record telemetry metric for a request."""
        pass

    @abstractmethod
    def query_metrics(self, since_iso: Optional[str] = None) -> List[RequestMetric]:
        """Retrieve metrics since a given ISO timestamp."""
        pass
