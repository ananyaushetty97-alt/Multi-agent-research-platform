from typing import TypedDict, Optional, List

class ResearchState(TypedDict):
    session_id: Optional[str]
    topic: str
    intent: Optional[str]                       # "new_research" | "modify" | "question"
    search_results: Optional[List[dict]]
    summary: Optional[str]
    report: Optional[str]
    verification_notes: Optional[str]
    is_verified: bool
    revision_count: int
    cache_hit: bool
    conversation_history: Optional[List[dict]]