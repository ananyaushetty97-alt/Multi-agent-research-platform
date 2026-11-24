"""
Safety monitoring and red-team evaluation routes.
"""
import asyncio
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
async def run_redteam_benchmark(
    fake_llm: bool = Query(False, description="Use offline fake LLM for fast testing"),
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    Trigger a new red-team benchmark run against the platform.
    Runs all 11 canonical attacks (6 indirect XPIA + 5 direct jailbreak).
    Uses PyRIT to orchestrate attacks with defenses enabled.
    """
    # Import here to avoid circular imports
    from redteam.run_redteam import run_redteam_benchmark as run_benchmark

    try:
        # Run the benchmark in a thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: run_benchmark(
                all_attacks=True,
                fake_llm=fake_llm,
                no_defense=False,
                no_pyrit=False,
            ),
        )

        # Load the fresh summary from the saved results
        summary = safety_service.load_redteam_summary()
        if not summary:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Benchmark completed but failed to load results.",
            )

        # Add fields expected by frontend for status display
        summary.attacks_completed = summary.total_attacks - summary.attacks_reached_user
        summary.attacks_errored = 0  # Could be enhanced to track actual errors

        return summary

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Red-team benchmark failed: {str(e)}",
        )
