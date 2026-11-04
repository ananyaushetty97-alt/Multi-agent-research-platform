"""
Memory and cache management routes.
Includes confirmation safeguards and audit logging for all destructive operations.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Request

from admin_backend.models.memory_cache import (
    CacheEntryItem,
    DestructiveActionResult,
    LTMReportItem,
    SessionMetadataItem,
)
from admin_backend.security.dependencies import (
    AuthenticatedUser,
    require_admin_role,
    require_destructive_confirmation,
)
from admin_backend.services.memory_cache_service import memory_cache_service

router = APIRouter(prefix="/memory", tags=["Admin Memory & Cache"])


# -----------------------------------------------------------------------------
# Long-Term Memory (Postgres)
# -----------------------------------------------------------------------------
@router.get("/reports", response_model=List[LTMReportItem])
def list_ltm_reports(
    query: Optional[str] = Query(None, description="Search term for report text or topic"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    Search and inspect archived research reports stored in PostgreSQL long-term memory.
    """
    return memory_cache_service.list_ltm_reports(query=query, limit=limit, offset=offset)


@router.delete("/reports/{report_id}", response_model=DestructiveActionResult)
def delete_ltm_report(
    report_id: str,
    request: Request,
    _confirmed: bool = Depends(require_destructive_confirmation),
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    Permanently delete a report from PostgreSQL long-term memory.
    DESTRUCTIVE: Requires '?confirm=true' query parameter or 'X-Confirm-Destructive: true' header.
    Audited in admin audit log.
    """
    client_ip = request.client.host if request.client else "unknown"
    return memory_cache_service.delete_ltm_report(
        report_id=report_id,
        actor_username=admin.username,
        actor_role=admin.role,
        client_ip=client_ip,
    )


# -----------------------------------------------------------------------------
# Semantic Cache (Redis)
# -----------------------------------------------------------------------------
@router.get("/cache", response_model=List[CacheEntryItem])
def list_cache_entries(
    limit: int = Query(50, ge=1, le=200),
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    List non-expired semantic cache entries currently stored in Redis.
    """
    return memory_cache_service.list_cache_entries(limit=limit)


@router.delete("/cache/{entry_id}", response_model=DestructiveActionResult)
def invalidate_cache_entry(
    entry_id: str,
    request: Request,
    _confirmed: bool = Depends(require_destructive_confirmation),
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    Invalidate an individual semantic cache entry immediately.
    DESTRUCTIVE: Requires '?confirm=true' query parameter or 'X-Confirm-Destructive: true' header.
    Audited in admin audit log.
    """
    client_ip = request.client.host if request.client else "unknown"
    return memory_cache_service.invalidate_cache_entry(
        entry_id=entry_id,
        actor_username=admin.username,
        actor_role=admin.role,
        client_ip=client_ip,
    )


@router.post("/cache/clear", response_model=DestructiveActionResult)
def clear_all_cache(
    request: Request,
    _confirmed: bool = Depends(require_destructive_confirmation),
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    Wipe all semantic cache entries across Redis.
    DESTRUCTIVE: Requires '?confirm=true' query parameter or 'X-Confirm-Destructive: true' header.
    Audited in admin audit log.
    """
    client_ip = request.client.host if request.client else "unknown"
    return memory_cache_service.clear_all_cache(
        actor_username=admin.username,
        actor_role=admin.role,
        client_ip=client_ip,
    )


# -----------------------------------------------------------------------------
# Short-Term Memory / Sessions (Redis)
# -----------------------------------------------------------------------------
@router.get("/sessions", response_model=List[SessionMetadataItem])
def list_active_sessions(
    limit: int = Query(50, ge=1, le=200),
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    Inspect active session metadata and TTL expiration in Redis.
    Privacy enforcement: conversation message bodies are NOT exposed.
    """
    return memory_cache_service.list_session_metadata(limit=limit)
