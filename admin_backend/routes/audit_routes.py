"""
Audit log inspection routes.
Requires administrator privileges.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query

from admin_backend.models.audit import (
    AuditAction, AuditLogEntry, AuditLogFilter,
    UserActivityAction, UserActivityLogEntry, UserActivityLogFilter
)
from admin_backend.security.dependencies import AuthenticatedUser, require_admin_role
from admin_backend.services.audit_service import audit_service

router = APIRouter(prefix="/audit", tags=["Admin Audit"])


@router.get("/logs", response_model=List[AuditLogEntry])
def list_audit_logs(
    actor: Optional[str] = Query(None, description="Filter by actor username or email"),
    action: Optional[AuditAction] = Query(None, description="Filter by action"),
    resource_type: Optional[str] = Query(None, description="Filter by target resource"),
    status: Optional[str] = Query(None, description="Filter by status ('success' or 'failure')"),
    start_date: Optional[str] = Query(None, description="Filter by start date (ISO 8601 or YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Filter by end date (ISO 8601 or YYYY-MM-DD)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    Query the administrative audit trail.
    Returns immutable records of admin actions, target resources, outcomes, and timestamps.
    """
    filter_opts = AuditLogFilter(
        actor=actor,
        action=action,
        resource_type=resource_type,
        status=status,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return audit_service.query(filter_opts)


@router.get("/user-activity", response_model=List[UserActivityLogEntry])
def list_user_activity_logs(
    username: Optional[str] = Query(None, description="Filter by username"),
    action: Optional[UserActivityAction] = Query(None, description="Filter by user action"),
    status: Optional[str] = Query(None, description="Filter by status"),
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    start_date: Optional[str] = Query(None, description="Filter by start date (ISO 8601)"),
    end_date: Optional[str] = Query(None, description="Filter by end date (ISO 8601)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    Query user activity logs.
    Returns records of user portal actions: research queries, logins, cache hits, guardrail blocks, etc.
    """
    filter_opts = UserActivityLogFilter(
        username=username,
        action=action,
        status=status,
        session_id=session_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return audit_service.query_user_activity(filter_opts)
