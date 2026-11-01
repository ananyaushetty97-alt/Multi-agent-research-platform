"""
Performance metrics and telemetry routes.
"""
from fastapi import APIRouter, Depends, Query

from admin_backend.models.metrics import LatencyPercentiles, MetricsSummary
from admin_backend.security.dependencies import AuthenticatedUser, require_admin_role
from admin_backend.services.metrics_service import metrics_service

router = APIRouter(prefix="/metrics", tags=["Admin Metrics"])


@router.get("/summary", response_model=MetricsSummary)
def get_metrics_summary(
    time_range: str = Query("24h", pattern="^(1h|24h|7d|all)$", description="Aggregation timeframe"),
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    Retrieve operational metrics summary including request counts, error rates,
    cache hit rates, provider fallbacks, 429 rate limits, search call counts,
    and average/p95 latencies.
    """
    return metrics_service.get_summary(time_range=time_range)


@router.get("/latency", response_model=LatencyPercentiles)
def get_latency_statistics(
    time_range: str = Query("24h", pattern="^(1h|24h|7d|all)$", description="Aggregation timeframe"),
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    Retrieve fine-grained latency distribution percentiles (avg, min, max, p50, p90, p95, p99).
    """
    summary = metrics_service.get_summary(time_range=time_range)
    return summary.latency
