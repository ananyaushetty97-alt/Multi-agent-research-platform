"""
Request tracing and agent step telemetry schemas.
Privacy-conscious: full user prompts are not stored; previews are redacted.
"""
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class AgentStepType(str, Enum):
    ROUTER = "router"
    SEARCH = "search"
    SUMMARIZE = "summarize"
    WRITE = "write"
    VERIFY = "verify"
    MODIFY = "modify"
    ANSWER = "answer"


class AgentStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentStepRecord(BaseModel):
    step_id: str
    step_type: AgentStepType
    status: AgentStepStatus
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: Optional[float] = None
    summary_excerpt: Optional[str] = Field(
        None,
        description="Redacted/shortened excerpt of agent output (max 160 chars)"
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Step metadata (e.g. revisions count, sources count)"
    )
    error_message: Optional[str] = None


class RequestOutcome(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    BLOCKED = "blocked"


class RequestTrace(BaseModel):
    request_id: str
    session_id: str
    intent: Optional[str] = "new_research"
    topic_preview: str = Field(..., description="Redacted/shortened topic query")
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: Optional[float] = None
    cache_status: str = "miss"  # "hit", "miss", "bypass"
    sources_count: int = 0
    overall_score: Optional[float] = None
    outcome: RequestOutcome = RequestOutcome.SUCCESS
    error_category: Optional[str] = None  # "guardrail_block", "llm_unavailable", "pipeline_error"
    provider: Optional[str] = None
    model: Optional[str] = None
    fallback_used: bool = False
    rate_limited_429: bool = False
    steps: List[AgentStepRecord] = Field(default_factory=list)


class TraceFilter(BaseModel):
    session_id: Optional[str] = None
    intent: Optional[str] = None
    outcome: Optional[RequestOutcome] = None
    min_duration_ms: Optional[float] = None
    error_category: Optional[str] = None
    limit: int = Field(50, ge=1, le=200)
    offset: int = Field(0, ge=0)
