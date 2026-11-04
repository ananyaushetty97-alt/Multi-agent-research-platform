"""
Quality scoring, LLM-as-a-judge evaluation, and human review schemas.
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class JudgeScoreRecord(BaseModel):
    id: str = Field(..., description="Unique record identifier")
    timestamp: str = Field(..., description="Grading timestamp")
    topic: str
    relevance: Optional[int] = Field(None, ge=1, le=10)
    accuracy: Optional[int] = Field(None, ge=1, le=10)
    clarity: Optional[int] = Field(None, ge=1, le=10)
    overall: Optional[float] = Field(None, ge=1.0, le=10.0)
    comment: Optional[str] = None
    is_failed_grading: bool = False
    error_message: Optional[str] = None
    suspected_truncated: bool = Field(
        False,
        description="Heuristic indicator that the generated report was cut short"
    )
    truncation_reason: Optional[str] = Field(
        None,
        description="Non-definitive heuristic reason (e.g. comment noted text was cut off)"
    )


class HumanReviewScore(BaseModel):
    review_id: str
    report_id: Optional[str] = None
    topic: str
    reviewer_username: str
    review_timestamp: str
    relevance: int = Field(..., ge=1, le=10)
    accuracy: int = Field(..., ge=1, le=10)
    clarity: int = Field(..., ge=1, le=10)
    overall: float = Field(..., ge=1.0, le=10.0)
    feedback_notes: Optional[str] = Field(None, max_length=1000)
    flagged_for_rerun: bool = False


class QualityFilter(BaseModel):
    min_overall: Optional[float] = None
    max_overall: Optional[float] = None
    only_failed: bool = False
    only_suspected_truncated: bool = False
    search_topic: Optional[str] = None
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)


class QualitySummary(BaseModel):
    total_records: int
    successful_grades: int
    failed_grades: int
    average_overall: Optional[float] = None
    average_relevance: Optional[float] = None
    average_accuracy: Optional[float] = None
    average_clarity: Optional[float] = None
    low_scoring_count: int  # e.g., overall < 7.0
    suspected_truncated_count: int
    human_reviews_count: int
