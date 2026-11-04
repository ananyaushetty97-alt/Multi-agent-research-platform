"""
Request and agent execution trace inspection routes.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from admin_backend.models.traces import RequestOutcome, RequestTrace, TraceFilter
from admin_backend.security.dependencies import AuthenticatedUser, require_admin_role
from admin_backend.services.trace_service import trace_service

router = APIRouter(prefix="/traces", tags=["Admin Traces"])


@router.get("", response_model=List[RequestTrace])
def list_request_traces(
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    intent: Optional[str] = Query(None, description="Filter by intent (new_research, modify, question)"),
    outcome: Optional[RequestOutcome] = Query(None, description="Filter by outcome"),
    min_duration_ms: Optional[float] = Query(None, description="Filter by minimum duration"),
    error_category: Optional[str] = Query(None, description="Filter by error category"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    List request traces with metadata (request ID, timing, cache status, sources, outcome).
    Does NOT store or expose full unredacted user prompts.
    """
    filter_opts = TraceFilter(
        session_id=session_id,
        intent=intent,
        outcome=outcome,
        min_duration_ms=min_duration_ms,
        error_category=error_category,
        limit=limit,
        offset=offset,
    )
    return trace_service.query_traces(filter_opts)


@router.get("/{request_id}", response_model=RequestTrace)
def get_request_trace_detail(
    request_id: str,
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    Retrieve deep telemetry trace for a single request, including individual agent-step
    timings and status for Search, Summarize, Write, Verify, Modify, and Answer.
    """
    trace = trace_service.get_trace(request_id)
    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Request trace '{request_id}' not found",
        )
    return trace
