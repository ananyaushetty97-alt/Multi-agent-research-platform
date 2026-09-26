from typing import TypedDict, Optional

class ResearchState(TypedDict):
    topic: str
    search_results: Optional[str]
    summary: Optional[str]
    report: Optional[str]
    verification_notes: Optional[str]
    is_verified: bool
    revision_count: int