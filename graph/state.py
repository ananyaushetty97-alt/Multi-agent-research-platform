from typing import TypedDict, Optional, List

class ResearchState(TypedDict):
    topic: str
    search_results: Optional[List[dict]]
    summary: Optional[str]
    report: Optional[str]
    verification_notes: Optional[str]
    is_verified: bool
    revision_count: int
    cache_hit: bool