"""
Safety monitoring and red-team evaluation routes.
"""
import subprocess
import sys
import logging
import os
import re
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from admin_backend.models.safety import (
    GuardCheckType,
    RedTeamRunSummary,
    SafetyEvent,
    SafetyEventFilter,
    SafetyOutcome,
)
from admin_backend.security.dependencies import AuthenticatedUser, require_admin_role
from admin_backend.services.safety_service import safety_service

router = APIRouter(prefix="/safety", tags=["Admin Safety"])
log = logging.getLogger("admin_backend.safety.redteam")


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


@router.get("/events", response_model=List[SafetyEvent])
def list_safety_events(
    check_type: Optional[GuardCheckType] = Query(None, description="Filter by guardrail layer"),
    outcome: Optional[SafetyOutcome] = Query(None, description="Filter by safety outcome"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    List recorded guardrail block and sanitization events.
    Excerpts are strictly truncated to protect privacy and avoid retaining harmful content.
    """
    filter_opts = SafetyEventFilter(
        check_type=check_type,
        outcome=outcome,
        limit=limit,
        offset=offset,
    )
    return safety_service.query_safety_events(filter_opts)


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


@router.post("/redteam/run", response_model=RedTeamRunSummary)
def run_live_redteam(admin: AuthenticatedUser = Depends(require_admin_role)):
    """
    Execute bounded, fixed-vector tests against this application's request guard and
    LangGraph agents using the configured LLM provider. No defenses are disabled.
    """
    root = Path(__file__).resolve().parents[2]
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "redteam.run_redteam", "--all"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else exc.stderr
        log.error("Live PyRIT subprocess timed out; stderr: %s", _redact_process_diagnostic(stderr))
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
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Live PyRIT benchmark could not start or persist results. Check configured LLM and PyRIT dependencies.",
        )

    summary = safety_service.load_redteam_summary()
    if not summary:
        log.error("Live PyRIT subprocess exited successfully but no valid result summary was persisted")
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
    return summary
