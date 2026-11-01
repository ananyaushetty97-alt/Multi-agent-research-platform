"""
Unit tests for request metrics telemetry and latency statistics.
"""
from admin_backend.services.metrics_service import MetricsService
from admin_backend.storage.in_memory import InMemoryMetricStorage


def test_empty_metrics():
    storage = InMemoryMetricStorage()
    svc = MetricsService(storage=storage)
    summary = svc.get_summary(time_range="24h")

    assert summary.total_requests == 0
    assert summary.latency.avg_ms == 0.0
    assert summary.error_rate_pct == 0.0


def test_metrics_aggregation_and_percentiles():
    storage = InMemoryMetricStorage()
    svc = MetricsService(storage=storage)

    # Record 10 sample requests with known durations
    durations = [100.0, 150.0, 200.0, 250.0, 300.0, 350.0, 400.0, 450.0, 500.0, 1000.0]
    for i, dur in enumerate(durations):
        svc.record_request(
            request_id=f"req-{i}",
            endpoint="/generate",
            method="POST",
            status_code=200 if i < 8 else 500,
            duration_ms=dur,
            cache_hit=(i % 3 == 0),
            provider_used="groq" if i < 9 else "ollama",
            model_used="qwen/qwen3.8-27b" if i < 9 else "qwen2.5:7b",
            fallback_occurred=(i == 9),
            search_called=True,
            timestamp_iso="2026-10-27T10:00:00Z",
        )

    summary = svc.get_summary(time_range="all")

    assert summary.total_requests == 10
    assert summary.successful_requests == 8
    assert summary.failed_requests == 2
    assert summary.error_rate_pct == 20.0
    assert summary.provider_fallbacks == 1
    assert summary.total_search_calls == 10

    # Latency percentiles check
    assert summary.latency.min_ms == 100.0
    assert summary.latency.max_ms == 1000.0
    assert summary.latency.avg_ms == 370.0
    assert summary.latency.p50_ms == 325.0
    assert summary.latency.p95_ms > 500.0

    # Grouping checks
    assert summary.requests_by_day.get("2026-10-27") == 10
    assert summary.provider_breakdown["groq"] == 9
    assert summary.provider_breakdown["ollama"] == 1
