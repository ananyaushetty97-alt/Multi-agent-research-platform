"""
Safety events and red-team evaluation schemas.
Strictly separates production safety incidents from offline red-team evaluations.
"""
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class GuardCheckType(str, Enum):
    INPUT_RULE = "input_rule"
    INPUT_LLM = "input_llm"
    OUTPUT_RULE = "output_rule"
    OUTPUT_LLM = "output_llm"
    SEARCH_XPIA = "search_xpia"  # Prompt injection filtered from search results


class SafetyOutcome(str, Enum):
    BLOCKED = "blocked"
    SANITIZED = "sanitized"
    FLAGGED = "flagged"


class SafetyEvent(BaseModel):
    event_id: str
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    timestamp: str  # ISO 8601 UTC
    check_type: GuardCheckType
    reason: str
    excerpt: str = Field(
        ...,
        max_length=200,
        description="Redacted snippet that triggered the guardrail"
    )
    outcome: SafetyOutcome = SafetyOutcome.BLOCKED
    details: Dict[str, Any] = Field(default_factory=dict)


class RedTeamAttackRecord(BaseModel):
    type: str  # "indirect" or "direct"
    payload_preview: str
    reached_user: bool
    canary_leaked: Optional[bool] = None
    verify_flagged: Optional[bool] = None
    guard_blocked: Optional[bool] = None
    reason: Optional[str] = None


class RedTeamRunSummary(BaseModel):
    run_id: str
    recorded_at: str
    source_file: str
    total_attacks: int
    attacks_defended: int
    attacks_reached_user: int
    defense_rate_pct: float
    indirect_count: int
    direct_count: int
    attacks: List[RedTeamAttackRecord] = Field(default_factory=list)


class SafetyEventFilter(BaseModel):
    check_type: Optional[GuardCheckType] = None
    outcome: Optional[SafetyOutcome] = None
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)
