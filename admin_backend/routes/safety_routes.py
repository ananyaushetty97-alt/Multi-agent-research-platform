"""
Safety monitoring and red-team evaluation routes.
"""
import subprocess
import sys
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
    Retrieve offline PyRIT red-team security attack simulation results.
    Strictly isolated from live production events.
    """
    summary = safety_service.load_redteam_summary()
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No red-team evaluation results found at logs/redteam_results.json. Run 'python -m redteam.run_redteam' to generate results.",
        )
    return summary


@router.post("/redteam/run", response_model=RedTeamRunSummary)
def run_offline_redteam(admin: AuthenticatedUser = Depends(require_admin_role)):
    """
    Execute the existing PyRIT offline fake-LLM benchmark with defenses enabled.
    This endpoint never exposes or toggles production defense settings.
    """
    root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "redteam.run_redteam",
            "--all",
            "--fake-llm",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if completed.returncode != 0:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Offline PyRIT benchmark failed",
        )

    summary = safety_service.load_redteam_summary()
    if not summary:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Offline PyRIT benchmark completed but results could not be persisted",
        )
    return summary
