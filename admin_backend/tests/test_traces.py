"""
Unit tests for request tracing, agent steps, and privacy redaction.
"""
from admin_backend.models.traces import AgentStepType, AgentStepStatus, RequestOutcome, TraceFilter
from admin_backend.services.trace_service import TraceService, _redact_text
from admin_backend.storage.in_memory import InMemoryTraceStorage


def test_privacy_redaction():
    text_with_pii = "Contact support@example.com or 555-123-4567 for info. " + ("A" * 300)
    redacted = _redact_text(text_with_pii, max_len=50, mask_pii=True)

    assert "[EMAIL]" in redacted
    assert "[PHONE]" in redacted
    assert len(redacted) <= 70
    assert "[truncated]" in redacted


def test_trace_collector_agent_steps():
    storage = InMemoryTraceStorage()
    svc = TraceService(storage=storage)

    collector = svc.start_trace(
        request_id="req-trace-01",
        session_id="session-xyz",
        topic="Recent advances in quantum computing",
    )

    with collector.step(AgentStepType.SEARCH, details={"query": "quantum computing 2026"}) as step:
        step.summary_excerpt = "Found 5 credible sources"

    with collector.step(AgentStepType.WRITE) as step:
        step.summary_excerpt = "Drafted 300 words"

    trace = collector.complete(
        outcome=RequestOutcome.SUCCESS,
        sources_count=5,
        overall_score=9.2,
        provider="groq",
        model="qwen/qwen3.8-27b",
    )

    assert trace.request_id == "req-trace-01"
    assert trace.duration_ms is not None
    assert len(trace.steps) == 2
    assert trace.steps[0].step_type == AgentStepType.SEARCH
    assert trace.steps[0].status == AgentStepStatus.COMPLETED
    assert trace.steps[1].step_type == AgentStepType.WRITE
    assert trace.steps[1].status == AgentStepStatus.COMPLETED

    # Fetch from storage
    stored = svc.get_trace("req-trace-01")
    assert stored is not None
    assert stored.sources_count == 5

    # Filter query
    results = svc.query_traces(TraceFilter(session_id="session-xyz"))
    assert len(results) == 1
    assert results[0].request_id == "req-trace-01"


def test_trace_step_failure():
    storage = InMemoryTraceStorage()
    svc = TraceService(storage=storage)
    collector = svc.start_trace("req-fail", "sess-1", "Failing topic")

    try:
        with collector.step(AgentStepType.VERIFY):
            raise ValueError("Claim mismatch error")
    except ValueError:
        pass

    assert len(collector.steps) == 1
    assert collector.steps[0].status == AgentStepStatus.FAILED
    assert "Claim mismatch" in (collector.steps[0].error_message or "")
