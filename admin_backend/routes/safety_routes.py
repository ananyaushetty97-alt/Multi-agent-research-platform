"""
Safety monitoring and red-team evaluation routes.
"""
import subprocess
import sys
import logging
import os
import re
import threading
from pathlib import Path
from typing import List, Literal, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status

from admin_backend.models.audit import AuditAction
from admin_backend.models.safety import (
    EventSource,
    GuardCheckType,
    RedTeamHistoryEntry,
    RedTeamRunRequest,
    RedTeamRunSummary,
    SafetyEvent,
    SafetyEventFilter,
    SafetyOutcome,
    SafetySummary,
)
from admin_backend.security.dependencies import AuthenticatedUser, require_admin_role
from admin_backend.services.audit_service import audit_service
from admin_backend.services.safety_service import safety_service

router = APIRouter(prefix="/safety", tags=["Admin Safety"])
log = logging.getLogger("admin_backend.safety.redteam")

# Only one red-team run at a time: two runs would overwrite each other's results file.
_redteam_run_lock = threading.Lock()

# Command-line flags for each case set the admin portal can start.
_RUN_SCOPE_ARGS = {
    "all": ["--all"],
    "direct": ["--direct-only"],
}

SourceParam = Literal["production", "redteam", "all"]


def _source_filter(source: str) -> Optional[EventSource]:
    if source == "all":
        return None
    return EventSource(source)


def _redact_process_diagnostic(text: Optional[str]) -> str:
    """Make subprocess diagnostics useful without writing configured credentials to logs."""
    diagnostic = text or ""
    for value in os.environ.values():
        if value and len(value) >= 8:
            diagnostic = diagnostic.replace(value, "[redacted]")
    diagnostic = re.sub(
        r"(?i)(api[_ -]?key|authorization|access[_ -]?token|password|secret)"
        r"(\s*[:=]\s*|\s+)[^\s,;]+",
        r"\1=[redacted]",
        diagnostic,
    )
    return diagnostic[-2000:]


def _audit_run(admin: AuthenticatedUser, request: Request, run_status: str, details: dict) -> None:
    """Record who started a red-team run. Auditing must never break the run itself."""
    client_ip = None
    if request.client:
        client_ip = request.client.host
    try:
        audit_service.log_action(
            actor_username=admin.username,
            actor_role=admin.role,
            action=AuditAction.REDTEAM_RUN,
            resource_type="redteam",
            resource_id=details.get("run_id"),
            status=run_status,
            details=details,
            client_ip=client_ip,
        )
    except Exception as exc:
        log.warning("Could not audit red-team run: %s", exc)


@router.get("/events", response_model=List[SafetyEvent])
def list_safety_events(
    check_type: Optional[GuardCheckType] = Query(None, description="Filter by guardrail layer"),
    outcome: Optional[SafetyOutcome] = Query(None, description="Filter by safety outcome"),
    source: SourceParam = Query(
        "production",
        description="production (default), redteam (events caused by red-team runs) or all",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    List recorded guardrail block and sanitization events.
    Excerpts are strictly truncated to protect privacy and avoid retaining harmful content.
    Red-team test traffic is excluded unless source=redteam or source=all.
    """
    filter_opts = SafetyEventFilter(
        check_type=check_type,
        outcome=outcome,
        source=_source_filter(source),
        limit=limit,
        offset=offset,
    )
    return safety_service.query_safety_events(filter_opts)


@router.get("/summary", response_model=SafetySummary)
def get_safety_summary(
    source: SourceParam = Query("production"),
    window_hours: int = Query(24, ge=1, le=24 * 90),
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """Counts by guardrail layer and outcome, plus how many events fall in the recent window."""
    return safety_service.summarize_events(source=_source_filter(source), window_hours=window_hours)


@router.get("/redteam", response_model=RedTeamRunSummary)
def get_redteam_summary(admin: AuthenticatedUser = Depends(require_admin_role)):
    """
    Retrieve the latest fixed-vector PyRIT red-team run.
    Strictly isolated from live production events.
    """
    summary = safety_service.load_redteam_summary()
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No red-team results found. Run the authenticated admin benchmark to create them.",
        )
    return summary


@router.get("/redteam/history", response_model=List[RedTeamHistoryEntry])
def get_redteam_history(
    limit: int = Query(20, ge=1, le=100),
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """Previous red-team runs (counts only), newest first."""
    return safety_service.load_redteam_history(limit=limit)


@router.get("/redteam/status")
def get_redteam_status(admin: AuthenticatedUser = Depends(require_admin_role)):
    """Whether a red-team run is currently in progress on this server."""
    return {"running": _redteam_run_lock.locked()}


@router.post("/redteam/run", response_model=RedTeamRunSummary)
def run_live_redteam(
    request: Request,
    run_request: Optional[RedTeamRunRequest] = Body(None),
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    Execute bounded, fixed-vector tests against this application's request guard and
    LangGraph agents using the configured LLM provider. No defenses are disabled.
    The request body is optional; without it every case is run (scope="all").
    """
    scope = (run_request or RedTeamRunRequest()).scope
    if not _redteam_run_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A red-team run is already in progress. Wait for it to finish.",
        )
    try:
        root = Path(__file__).resolve().parents[2]
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "redteam.run_redteam", *_RUN_SCOPE_ARGS[scope]],
                cwd=str(root),
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr
            log.error("Live PyRIT subprocess timed out; stderr: %s", _redact_process_diagnostic(stderr))
            _audit_run(admin, request, "failure", {"scope": scope, "error": "timeout"})
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Live PyRIT run timed out; inspect configured LLM availability and rerun if appropriate.",
            ) from exc
        if completed.returncode != 0:
            log.error(
                "Live PyRIT subprocess exited with code %s; stderr: %s",
                completed.returncode,
                _redact_process_diagnostic(completed.stderr),
            )
            _audit_run(admin, request, "failure", {"scope": scope, "exit_code": completed.returncode})
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Live PyRIT benchmark could not start or persist results. Check configured LLM and PyRIT dependencies.",
            )

        summary = safety_service.load_redteam_summary()
        if not summary:
            log.error("Live PyRIT subprocess exited successfully but no valid result summary was persisted")
            _audit_run(admin, request, "failure", {"scope": scope, "error": "no results persisted"})
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Live PyRIT benchmark completed but results could not be persisted",
            )
        log.info(
            "Live PyRIT run %s completed: %s defended, %s breached, %s errors",
            summary.run_id,
            summary.attacks_defended,
            summary.attacks_reached_user,
            summary.attacks_errored,
        )
        _audit_run(admin, request, "success", {
            "run_id": summary.run_id,
            "scope": scope,
            "total": summary.total_attacks,
            "defended": summary.attacks_defended,
            "breached": summary.attacks_reached_user,
            "errors": summary.attacks_errored,
        })
        return summary
    finally:
        _redteam_run_lock.release()
