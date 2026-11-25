"""
Safety events and red-team evaluation schemas.
Strictly separates production safety incidents from offline red-team evaluations.
"""
from enum import Enum
from typing import Optional, Dict, Any, List, Literal
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


class EventSource(str, Enum):
    """Where a safety event came from. Red-team test traffic is never mixed into production."""
    PRODUCTION = "production"
    REDTEAM = "redteam"


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
    # Older persisted events have no source field; they were real traffic.
    source: EventSource = EventSource.PRODUCTION
    details: Dict[str, Any] = Field(default_factory=dict)


class RedTeamAttackRecord(BaseModel):
    type: str  # "indirect" or "direct"
    payload_preview: str
    reached_user: bool
    status: Optional[str] = None
    error: Optional[str] = None
    reason: Optional[str] = None
    canary_leaked: Optional[bool] = None
    verify_flagged: Optional[bool] = None
    guard_blocked: Optional[bool] = None
    input_blocked: Optional[bool] = None
    revisions: Optional[int] = None


class RedTeamRunSummary(BaseModel):
    run_id: str
    recorded_at: str
    source_file: str
    mode: Optional[str] = None
    scope: Optional[str] = None
    defense_enabled: Optional[bool] = None
    total_attacks: int
    attacks_defended: int
    attacks_reached_user: int
    attacks_errored: int = 0
    attacks_completed: int = 0
    defense_rate_pct: float
    indirect_count: int
    direct_count: int
    attacks: List[RedTeamAttackRecord] = Field(default_factory=list)


class RedTeamHistoryEntry(BaseModel):
    """One line of the red-team run history (counts only, no payloads)."""
    run_id: str
    recorded_at: str
    mode: Optional[str] = None
    scope: Optional[str] = None
    defense_enabled: Optional[bool] = None
    total_attacks: int = 0
    attacks_defended: int = 0
    attacks_reached_user: int = 0
    attacks_errored: int = 0
    defense_rate_pct: float = 0.0


class RedTeamRunRequest(BaseModel):
    """Which fixed case set to run from the admin portal.

    all:    6 indirect (poisoned web page through the agents) + 5 direct jailbreaks
    direct: only the 5 direct jailbreaks through the input guard (fast, no agent LLM calls)
    """
    scope: Literal["all", "direct"] = "all"


class SafetyEventFilter(BaseModel):
    check_type: Optional[GuardCheckType] = None
    outcome: Optional[SafetyOutcome] = None
    # None returns events from every source
    source: Optional[EventSource] = EventSource.PRODUCTION
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)


class SafetySummary(BaseModel):
    """Counts for the Safety page tiles, computed from real recorded events."""
    source: str
    window_hours: int
    total_events: int
    events_in_window: int
    by_check_type: Dict[str, int] = Field(default_factory=dict)
    by_outcome: Dict[str, int] = Field(default_factory=dict)
    latest_event_at: Optional[str] = None
