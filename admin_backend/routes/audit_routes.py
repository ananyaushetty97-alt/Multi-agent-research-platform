"""
Audit log inspection routes.
Requires administrator privileges.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query

from admin_backend.models.audit import AuditAction, AuditLogEntry, AuditLogFilter
from admin_backend.security.dependencies import AuthenticatedUser, require_admin_role
from admin_backend.services.audit_service import audit_service

router = APIRouter(prefix="/audit", tags=["Admin Audit"])


@router.get("/logs", response_model=List[AuditLogEntry])
def list_audit_logs(
    actor: Optional[str] = Query(None, description="Filter by actor username"),
    action: Optional[AuditAction] = Query(None, description="Filter by action"),
    resource_type: Optional[str] = Query(None, description="Filter by target resource"),
    status: Optional[str] = Query(None, description="Filter by status ('success' or 'failure')"),
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
        limit=limit,
        offset=offset,
    )
    return audit_service.query(filter_opts)
