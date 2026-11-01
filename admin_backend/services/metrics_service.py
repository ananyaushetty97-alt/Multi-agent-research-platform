"""
Metrics collection and aggregation service.
Computes latency statistics (avg, p50, p90, p95, p99), error rates,
cache hit rates, provider fallbacks, 429 rate limits, and volume by day.
"""
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from admin_backend.models.metrics import (
    LatencyPercentiles,
    MetricsSummary,
    RequestMetric,
)
from admin_backend.storage.in_memory import InMemoryMetricStorage
from admin_backend.storage.interfaces import MetricStorageInterface


def _percentile(sorted_data: List[float], p: float) -> float:
    """Calculate the p-th percentile (0 <= p <= 100) from sorted numbers."""
    if not sorted_data:
        return 0.0
    if len(sorted_data) == 1:
        return sorted_data[0]
    rank = (p / 100.0) * (len(sorted_data) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    weight = rank - lower
    return round(sorted_data[lower] * (1.0 - weight) + sorted_data[upper] * weight, 2)


class MetricsService:
    def __init__(self, storage: Optional[MetricStorageInterface] = None):
        self.storage = storage or InMemoryMetricStorage()

    def record_request(
        self,
        request_id: str,
        endpoint: str,
        method: str,
        status_code: int,
        duration_ms: float,
        cache_hit: bool = False,
        provider_used: Optional[str] = None,
        model_used: Optional[str] = None,
        fallback_occurred: bool = False,
        is_rate_limited_429: bool = False,
        search_called: bool = False,
        timestamp_iso: Optional[str] = None,
    ) -> RequestMetric:
        """Record an individual request event."""
        now_iso = timestamp_iso or datetime.now(timezone.utc).isoformat()
        metric = RequestMetric(
            request_id=request_id,
            timestamp=now_iso,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            duration_ms=round(duration_ms, 2),
            cache_hit=cache_hit,
            provider_used=provider_used,
            model_used=model_used,
            fallback_occurred=fallback_occurred,
            is_rate_limited_429=is_rate_limited_429 or (status_code == 429),
            search_called=search_called,
        )
        self.storage.record_metric(metric)
        return metric

    def get_summary(self, time_range: str = "24h") -> MetricsSummary:
        """
        Aggregate stored metrics over the given time range.
        time_range options: '1h', '24h', '7d', 'all'
        """
        now = datetime.now(timezone.utc)
        since_iso: Optional[str] = None

        if time_range == "1h":
            since_iso = (now - timedelta(hours=1)).isoformat()
        elif time_range == "24h":
            since_iso = (now - timedelta(days=1)).isoformat()
        elif time_range == "7d":
            since_iso = (now - timedelta(days=7)).isoformat()

        metrics = self.storage.query_metrics(since_iso=since_iso)

        total_requests = len(metrics)
        if total_requests == 0:
            return MetricsSummary(
                time_range=time_range,
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
                error_rate_pct=0.0,
                cache_hits=0,
                cache_hit_rate_pct=0.0,
                provider_fallbacks=0,
                rate_limits_429=0,
                total_search_calls=0,
                latency=LatencyPercentiles(
                    count=0, avg_ms=0.0, min_ms=0.0, max_ms=0.0,
                    p50_ms=0.0, p90_ms=0.0, p95_ms=0.0, p99_ms=0.0
                ),
                requests_by_day={},
                provider_breakdown={},
                model_breakdown={},
            )

        durations = sorted(m.duration_ms for m in metrics)
        failed_count = sum(1 for m in metrics if m.status_code >= 400)
        cache_hits = sum(1 for m in metrics if m.cache_hit)
        fallbacks = sum(1 for m in metrics if m.fallback_occurred)
        rate_limits = sum(1 for m in metrics if m.is_rate_limited_429 or m.status_code == 429)
        searches = sum(1 for m in metrics if m.search_called)

        by_day: Dict[str, int] = defaultdict(int)
        by_provider: Dict[str, int] = defaultdict(int)
        by_model: Dict[str, int] = defaultdict(int)

        for m in metrics:
            day_str = m.timestamp[:10]
            by_day[day_str] += 1
            if m.provider_used:
                by_provider[m.provider_used] += 1
            if m.model_used:
                by_model[m.model_used] += 1

        avg_lat = round(sum(durations) / total_requests, 2)
        latency_stats = LatencyPercentiles(
            count=total_requests,
            avg_ms=avg_lat,
            min_ms=round(durations[0], 2),
            max_ms=round(durations[-1], 2),
            p50_ms=_percentile(durations, 50),
            p90_ms=_percentile(durations, 90),
            p95_ms=_percentile(durations, 95),
            p99_ms=_percentile(durations, 99),
        )

        return MetricsSummary(
            time_range=time_range,
            total_requests=total_requests,
            successful_requests=total_requests - failed_count,
            failed_requests=failed_count,
            error_rate_pct=round((failed_count / total_requests) * 100, 2),
            cache_hits=cache_hits,
            cache_hit_rate_pct=round((cache_hits / total_requests) * 100, 2),
            provider_fallbacks=fallbacks,
            rate_limits_429=rate_limits,
            total_search_calls=searches,
            latency=latency_stats,
            requests_by_day=dict(sorted(by_day.items())),
            provider_breakdown=dict(by_provider),
            model_breakdown=dict(by_model),
        )


def _seed_default_metrics(svc: MetricsService):
    now = datetime.now(timezone.utc)
    sample_runs = [
        (1, 3740.0, False, "groq", "llama-3.3-70b-versatile", False, True, 5),
        (2, 140.0, True, "groq", "llama-3.3-70b-versatile", False, False, 12),
        (3, 3450.0, False, "groq", "llama-3.3-70b-versatile", False, True, 20),
        (4, 3200.0, False, "groq", "llama-3.3-70b-versatile", False, True, 28),
        (5, 3820.0, False, "groq", "llama-3.3-70b-versatile", False, True, 35),
        (6, 2400.0, False, "groq", "llama-3.3-70b-versatile", False, True, 45),
        (7, 4220.0, False, "groq", "llama-3.3-70b-versatile", False, True, 55),
        (8, 2650.0, False, "groq", "llama-3.3-70b-versatile", False, True, 70),
        (9, 2100.0, True, "groq", "llama-3.3-70b-versatile", False, False, 90),
        (10, 3100.0, True, "groq", "llama-3.3-70b-versatile", False, False, 120),
        (11, 4120.0, False, "ollama", "llama-3.2:latest", True, True, 180),
    ]
    for idx, dur, hit, prov, mod, fb, search, mins_ago in sample_runs:
        ts_iso = (now - timedelta(minutes=mins_ago)).isoformat()
        svc.record_request(
            request_id=f"run-{idx:02d}",
            endpoint="/generate",
            method="POST",
            status_code=200,
            duration_ms=dur,
            cache_hit=hit,
            provider_used=prov,
            model_used=mod,
            fallback_occurred=fb,
            search_called=search,
            timestamp_iso=ts_iso,
        )


metrics_service = MetricsService()
_seed_default_metrics(metrics_service)


