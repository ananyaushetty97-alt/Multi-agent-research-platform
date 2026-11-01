"""
Memory, semantic cache, and session management schemas.
Enforces privacy: session contents are omitted by default; previews are limited.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class LTMReportItem(BaseModel):
    id: str
    topic: Optional[str] = None
    created_at: str
    preview: str = Field(..., description="Truncated text preview (max 160 chars)")
    sources_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CacheEntryItem(BaseModel):
    entry_id: str
    topic: str
    cached_at: Optional[float] = None
    cached_at_iso: Optional[str] = None
    ttl_remaining_seconds: Optional[int] = None
    preview: str = Field(..., description="Truncated preview of cached report")


class SessionMetadataItem(BaseModel):
    session_id: str
    turn_count: int
    last_turn_role: Optional[str] = None
    has_final_report: bool = False
    ttl_seconds_remaining: Optional[int] = None


class DestructiveActionResult(BaseModel):
    action: str
    target_id: Optional[str] = None
    affected_count: int = 1
    status: str = "completed"
    message: str
    audit_event_id: str
