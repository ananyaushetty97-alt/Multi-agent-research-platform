"""
Request metrics and performance telemetry schemas.
"""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class RequestMetric(BaseModel):
    request_id: str
    timestamp: str  # ISO 8601
    endpoint: str
    method: str = "POST"
    status_code: int
    duration_ms: float
    cache_hit: bool = False
    provider_used: Optional[str] = None  # e.g., "groq", "ollama"
    model_used: Optional[str] = None
    fallback_occurred: bool = False
    is_rate_limited_429: bool = False
    search_called: bool = False


class LatencyPercentiles(BaseModel):
    count: int
    avg_ms: float
    min_ms: float
    max_ms: float
    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float


class MetricsSummary(BaseModel):
    time_range: str  # "1h", "24h", "7d", "all"
    total_requests: int
    successful_requests: int
    failed_requests: int
    error_rate_pct: float
    cache_hits: int
    cache_hit_rate_pct: float
    provider_fallbacks: int
    rate_limits_429: int
    total_search_calls: int
    latency: LatencyPercentiles
    requests_by_day: Dict[str, int]
    provider_breakdown: Dict[str, int]
    model_breakdown: Dict[str, int]
