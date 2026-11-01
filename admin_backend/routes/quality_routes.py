"""
Quality scoring, LLM-as-a-judge history, and human evaluation review routes.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Request

from admin_backend.models.audit import AuditAction
from admin_backend.models.quality import (
    HumanReviewScore,
    JudgeScoreRecord,
    QualityFilter,
    QualitySummary,
)
from admin_backend.security.dependencies import AuthenticatedUser, require_admin_role
from admin_backend.services.audit_service import audit_service
from admin_backend.services.quality_service import quality_service

router = APIRouter(prefix="/quality", tags=["Admin Quality"])


@router.get("/scores", response_model=List[JudgeScoreRecord])
def get_evaluation_scores(
    min_overall: Optional[float] = Query(None, ge=1.0, le=10.0),
    max_overall: Optional[float] = Query(None, ge=1.0, le=10.0),
    only_failed: bool = Query(False, description="Filter only failed grading runs"),
    only_suspected_truncated: bool = Query(False, description="Filter only reports suspected of truncation"),
    search_topic: Optional[str] = Query(None, description="Search by topic substring"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    Query automated LLM-as-a-judge score history from logs/scores.jsonl.
    Supports filtering by score thresholds, failed evaluations, and suspected truncation heuristics.
    """
    filter_opts = QualityFilter(
        min_overall=min_overall,
        max_overall=max_overall,
        only_failed=only_failed,
        only_suspected_truncated=only_suspected_truncated,
        search_topic=search_topic,
        limit=limit,
        offset=offset,
    )
    return quality_service.query_scores(filter_opts)


@router.get("/summary", response_model=QualitySummary)
def get_quality_summary(admin: AuthenticatedUser = Depends(require_admin_role)):
    """
    Retrieve aggregate statistics across automated evaluations:
    average scores per criterion (relevance, accuracy, clarity),
    low-scoring report count, failed evaluation count, and suspected truncation counts.
    """
    return quality_service.get_quality_summary()


class HumanReviewSubmission(QualitySummary.__base__):
    pass


from pydantic import BaseModel, Field


class HumanReviewCreateRequest(BaseModel):
    topic: str
    relevance: int = Field(..., ge=1, le=10)
    accuracy: int = Field(..., ge=1, le=10)
    clarity: int = Field(..., ge=1, le=10)
    report_id: Optional[str] = None
    feedback_notes: Optional[str] = Field(None, max_length=1000)
    flagged_for_rerun: bool = False


@router.post("/human-reviews", response_model=HumanReviewScore)
def create_human_review(
    review_req: HumanReviewCreateRequest,
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    Submit a human evaluation review for a generated report.
    Kept strictly isolated from automated judge scores.
    """
    review = quality_service.add_human_review(
        topic=review_req.topic,
        reviewer_username=admin.username,
        relevance=review_req.relevance,
        accuracy=review_req.accuracy,
        clarity=review_req.clarity,
        report_id=review_req.report_id,
        feedback_notes=review_req.feedback_notes,
        flagged_for_rerun=review_req.flagged_for_rerun,
    )

    client_ip = request.client.host if request.client else "unknown"
    audit_service.log_action(
        actor_username=admin.username,
        actor_role=admin.role,
        action=AuditAction.HUMAN_REVIEW_ADD,
        resource_type="human_review",
        resource_id=review.review_id,
        status="success",
        details={"topic": review_req.topic, "overall": review.overall},
        client_ip=client_ip,
    )

    return review


@router.get("/human-reviews", response_model=List[HumanReviewScore])
def list_human_reviews(admin: AuthenticatedUser = Depends(require_admin_role)):
    """
    List all recorded human reviews.
    """
    return quality_service.list_human_reviews()
