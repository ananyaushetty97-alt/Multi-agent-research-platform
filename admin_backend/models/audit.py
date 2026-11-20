"""
Audit logging schemas for recording administrator actions and user activity.
"""
from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class AuditAction(str, Enum):
    AUTH_LOGIN = "auth.login"
    AUTH_LOGIN_FAILED = "auth.login_failed"
    USER_PROVISION = "user.provision"
    CACHE_INVALIDATE = "cache.invalidate"
    CACHE_CLEAR = "cache.clear"
    LTM_REPORT_DELETE = "ltm.report_delete"
    SESSION_DELETE = "session.delete"
    CONFIG_READ = "config.read"
    CONFIG_UPDATE = "config.update"
    EXPORT_DATA = "export.data"
    HUMAN_REVIEW_ADD = "quality.human_review_add"


class AuditLogEntry(BaseModel):
    id: str = Field(..., description="Unique event ID")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    actor_username: str = Field(..., description="Admin or user who triggered action")
    actor_role: str = Field(..., description="Role at time of action")
    action: AuditAction = Field(..., description="Operation performed")
    resource_type: str = Field(..., description="Type of target resource (e.g. cache, ltm_report, export)")
    resource_id: Optional[str] = Field(None, description="Identifier of target record")
    status: str = Field("success", description="'success' or 'failure'")
    details: Dict[str, Any] = Field(default_factory=dict, description="Metadata; no secrets or tokens")
    client_ip: Optional[str] = Field(None, description="Client IP address")


class AuditLogFilter(BaseModel):
    actor: Optional[str] = None
    action: Optional[AuditAction] = None
    resource_type: Optional[str] = None
    status: Optional[str] = None
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


# User Activity Log Models (separate from admin audit logs)
class UserActivityAction(str, Enum):
    RESEARCH_QUERY = "research.query"
    FOLLOWUP_QUESTION = "followup.question"
    REPORT_VIEW = "report.view"
    REPORT_EXPORT = "report.export"
    SESSION_START = "session.start"
    SESSION_END = "session.end"
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    CACHE_HIT = "cache.hit"
    CACHE_MISS = "cache.miss"
    GUARDRAIL_BLOCK = "guardrail.block"
    GUARDRAIL_PASS = "guardrail.pass"


class UserActivityLogEntry(BaseModel):
    id: str = Field(..., description="Unique event ID")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    session_id: str = Field(..., description="User session ID")
    username: str = Field(..., description="User who performed action")
    email: Optional[str] = Field(None, description="User email")
    action: UserActivityAction = Field(..., description="User activity performed")
    topic: Optional[str] = Field(None, description="Research topic if applicable")
    status: str = Field("success", description="'success', 'blocked', 'failed'")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    client_ip: Optional[str] = Field(None, description="Client IP address")
    user_agent: Optional[str] = Field(None, description="Client user agent")


class UserActivityLogFilter(BaseModel):
    username: Optional[str] = None
    action: Optional[UserActivityAction] = None
    status: Optional[str] = None
    session_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)
