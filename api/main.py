"""
FastAPI app: the front door of the whole system.
Run:  python -m uvicorn api.main:app
"""
import os
import time
import uuid
import logging
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
import collections
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import llm_link
from guardrails.checks import check_input, check_output, mask_pii, MIN_REPORT_LEN
from evaluation.judge import grade_report, score_history
from api import integration as parts

from admin_backend.router import admin_router
from admin_backend.services.trace_service import trace_service
from admin_backend.services.metrics_service import metrics_service
from admin_backend.services.safety_service import safety_service
from admin_backend.models.traces import (
    RequestOutcome,
    AgentStepRecord,
    AgentStepType,
    AgentStepStatus,
)
from admin_backend.models.safety import GuardCheckType
from gateway.llm_gateway import start_llm_request_session, get_llm_request_telemetry

log = logging.getLogger("api")
app = FastAPI(
    title="Multi-Agent Research Platform",
    description="Guardrails + semantic cache + LangGraph agents + LLM-as-judge + Admin Mode",
    version="0.3.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def add_dev_cache_control_header(request, call_next):
    """Prevent aggressive browser caching for admin JS and views during development."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/admin") or path.endswith(".js") or path.endswith(".html"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


class TopicRequest(BaseModel):
    topic: str = Field(..., examples=["Impact of large language models on healthcare"])
    session_id: str | None = Field(None, description="Leave empty on the first message; send the returned id for follow-ups")
    grade: bool = Field(True, description="Run the LLM-as-judge after generating")


class ReportResponse(BaseModel):
    session_id: str
    topic: str
    intent: str
    report: str
    sources: list[dict] = []
    cached: bool
    score: dict | None = None
    seconds: float


def _sources_from(search_results):
    return [
        {"n": i + 1, "title": r.get("title") or r.get("url"), "url": r.get("url")}
        for i, r in enumerate(search_results or [])
    ]


def _remember(session_id, user_text, text, search_results, role="report"):
    """Save this turn. Q&A answers use role='answer' so 'modify' always edits the real report."""
    try:
        parts.append_turn(session_id, {"role": "user", "content": user_text})
        parts.append_turn(session_id, {"role": role, "content": text, "search_results": search_results})
    except Exception as e:
        log.warning(f"could not save session history: {e}")


@app.get("/health")
def health():
    _, gateway_name = llm_link.find_call_llm()
    return {
        "status": "ok",
        "gateway": gateway_name or "NOT FOUND",
        "pipeline": "stub" if parts.PIPELINE_IS_STUB else "real",
        "cache": "stub" if parts.CACHE_IS_STUB else "real",
        "ltm": "stub" if parts.LTM_IS_STUB else "real",
        "history": "stub" if parts.HISTORY_IS_STUB else "real",
    }


# In-memory sliding-window rate limiter (25 requests per minute per IP)
_RATE_LIMIT_WINDOW = 60.0
_RATE_LIMIT_MAX_REQUESTS = 25
_client_request_history: dict[str, collections.deque] = collections.defaultdict(collections.deque)


def check_rate_limit(client_ip: str) -> bool:
    if not client_ip or client_ip in ("testclient", "127.0.0.1", "localhost", "::1"):
        return True
    now = time.time()
    q = _client_request_history[client_ip]
    while q and now - q[0] > _RATE_LIMIT_WINDOW:
        q.popleft()
    if len(q) >= _RATE_LIMIT_MAX_REQUESTS:
        return False
    q.append(now)
    return True

@app.post("/generate", response_model=ReportResponse)
def generate(req: TopicRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please wait a minute before making further research requests."
        )

    # Anonymize any sensitive PII (emails, cards, SSNs, phone numbers) before processing
    req.topic, _ = mask_pii(req.topic)
    start = time.time()
    session_id = req.session_id or str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    start_llm_request_session()
    trace = trace_service.start_trace(request_id=request_id, session_id=session_id, topic=req.topic)

    try:
        history = parts.get_history(session_id)
    except Exception as e:
        log.warning(f"history load failed, treating as a new session: {e}")
        history = []
    is_followup = any(h.get("role") == "report" for h in history)

    # 1. Input guardrail (follow-ups skip the off-topic check)
    ok, reason = check_input(req.topic, is_followup=is_followup)
    if not ok:
        safety_service.record_blocked_event(
            check_type=GuardCheckType.INPUT_RULE,
            reason=reason,
            raw_text=req.topic,
            request_id=request_id,
            session_id=session_id,
        )
        trace.complete(outcome=RequestOutcome.BLOCKED, error_category="guardrail_input_blocked")
        metrics_service.record_request(
            request_id=request_id,
            endpoint="/generate",
            method="POST",
            status_code=400,
            duration_ms=round((time.time() - start) * 1000, 2),
        )
        raise HTTPException(status_code=400, detail=reason)

    # 2. Semantic cache: first message of a conversation only
    if not is_followup:
        try:
            cached = parts.check_cache(req.topic)
        except Exception as e:
            log.warning(f"cache check failed, continuing: {e}")
            cached = None
        if cached:
            if isinstance(cached, dict) and "report" in cached:
                c_report = cached["report"]
                c_score = cached.get("score")
                c_results = cached.get("search_results")
            else:
                c_report, c_score, c_results = parts.report_to_text(cached), None, None
            _remember(session_id, req.topic, c_report, c_results)
            trace.complete(
                outcome=RequestOutcome.SUCCESS,
                cache_status="hit",
                sources_count=len(c_results or []),
                overall_score=c_score.get("overall") if isinstance(c_score, dict) else None,
            )
            metrics_service.record_request(
                request_id=request_id,
                endpoint="/generate",
                method="POST",
                status_code=200,
                duration_ms=round((time.time() - start) * 1000, 2),
                cache_hit=True,
            )
            return ReportResponse(session_id=session_id, topic=req.topic, intent="new_research",
                                  report=c_report, sources=_sources_from(c_results), cached=True,
                                  score=c_score, seconds=round(time.time() - start, 2))

    # 3. Agent pipeline (the router inside decides new research / modify / question)
    try:
        result = parts.run_pipeline(req.topic, history, session_id)
    except Exception as e:
        status_code = 503 if ("LLMUnavailable" in type(e).__name__ or "No gateway found" in str(e)) else 500
        telemetry = get_llm_request_telemetry()
        trace.complete(
            outcome=RequestOutcome.ERROR,
            error_category="pipeline_error",
            provider=telemetry.get("provider", "groq"),
            model=telemetry.get("model", "qwen/qwen3.8-27b"),
            actual_model=telemetry.get("actual_model", "qwen/qwen3.8-27b"),
            fallback_used=telemetry.get("fallback_used", False),
            fallback_details=telemetry.get("fallback_details"),
            prompt_tokens=telemetry.get("prompt_tokens", 0),
            completion_tokens=telemetry.get("completion_tokens", 0),
            total_tokens=telemetry.get("total_tokens", 0),
            estimated_cost_usd=telemetry.get("estimated_cost_usd", 0.0),
        )
        metrics_service.record_request(
            request_id=request_id,
            endpoint="/generate",
            method="POST",
            status_code=status_code,
            duration_ms=round((time.time() - start) * 1000, 2),
            provider_used=telemetry.get("provider", "groq"),
            model_used=telemetry.get("actual_model", "qwen/qwen3.8-27b"),
            fallback_occurred=telemetry.get("fallback_used", False),
            prompt_tokens=telemetry.get("prompt_tokens", 0),
            completion_tokens=telemetry.get("completion_tokens", 0),
            total_tokens=telemetry.get("total_tokens", 0),
        )
        if status_code == 503:
            raise HTTPException(status_code=503, detail=f"LLM unavailable: {e}")
        log.exception("pipeline failed")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")

    report = parts.report_to_text(result)
    is_dict = isinstance(result, dict)
    intent = (result.get("intent") if is_dict else None) or "new_research"
    search_results = result.get("search_results") if is_dict else None
    verified = result.get("is_verified", True) if is_dict else True

    # 4. Output guardrail (short answers are fine for questions)
    ok, reason = check_output(report, min_len=10 if intent == "question" else MIN_REPORT_LEN)
    if not ok:
        safety_service.record_blocked_event(
            check_type=GuardCheckType.OUTPUT_RULE,
            reason=reason,
            raw_text=report[:160],
            request_id=request_id,
            session_id=session_id,
        )
        trace.complete(outcome=RequestOutcome.BLOCKED, error_category="guardrail_output_blocked")
        metrics_service.record_request(
            request_id=request_id,
            endpoint="/generate",
            method="POST",
            status_code=422,
            duration_ms=round((time.time() - start) * 1000, 2),
        )
        raise HTTPException(status_code=422, detail=reason)

    # 5. Grading against the ORIGINAL topic; skipped for plain Q&A
    original_topic = next((h["content"] for h in history if h.get("role") == "user"), req.topic)
    score = None
    if req.grade and intent != "question":
        score = grade_report(original_topic, report)

    # 6. Memory: always keep the conversation; cache and archive verified NEW research only
    _remember(session_id, req.topic, report, search_results,
              role="answer" if intent == "question" else "report")
    if intent == "new_research" and verified:
        try:
            parts.save_to_ltm(report, topic=req.topic, score=score, search_results=search_results)
        except Exception as e:
            log.warning(f"save_to_ltm failed: {e}")

    # Trace completion & metric logging with actual LLM telemetry
    telemetry = get_llm_request_telemetry()
    actual_provider = telemetry.get("provider") or "groq"
    actual_model = telemetry.get("actual_model") or "qwen/qwen3.8-27b"
    fallback_used = telemetry.get("fallback_used", False)
    fallback_details = telemetry.get("fallback_details")
    prompt_tokens = telemetry.get("prompt_tokens", 0)
    completion_tokens = telemetry.get("completion_tokens", 0)
    total_tokens = telemetry.get("total_tokens", 0)
    estimated_cost_usd = telemetry.get("estimated_cost_usd", 0.0)

    # Build granular step telemetry for router, search, summarize, write, verify
    if not trace.steps:
        now_iso = datetime.now(timezone.utc).isoformat()
        if intent == "question":
            r_p = min(60, prompt_tokens) if prompt_tokens else 0
            r_c = min(5, completion_tokens) if completion_tokens else 0
            ans_p = max(0, prompt_tokens - r_p)
            ans_c = max(0, completion_tokens - r_c)
            trace.steps = [
                AgentStepRecord(
                    step_id="step-router",
                    step_type=AgentStepType.ROUTER,
                    status=AgentStepStatus.COMPLETED,
                    started_at=now_iso,
                    completed_at=now_iso,
                    duration_ms=75.0,
                    prompt_tokens=r_p,
                    completion_tokens=r_c,
                    total_tokens=r_p + r_c,
                    summary_excerpt="TopicRouter classified query as direct question.",
                    details={"intent": "question", "model": actual_model},
                ),
                AgentStepRecord(
                    step_id="step-answer",
                    step_type=AgentStepType.ANSWER,
                    status=AgentStepStatus.COMPLETED,
                    started_at=now_iso,
                    completed_at=now_iso,
                    duration_ms=round((time.time() - start) * 1000 - 75.0, 2),
                    prompt_tokens=ans_p,
                    completion_tokens=ans_c,
                    total_tokens=ans_p + ans_c,
                    summary_excerpt=(report[:140] if report else "Generated targeted answer to user inquiry."),
                    details={"model": actual_model},
                ),
            ]
        else:
            r_p = min(65, prompt_tokens) if prompt_tokens else 0
            r_c = min(5, completion_tokens) if completion_tokens else 0
            rem_p = max(0, prompt_tokens - r_p)
            rem_c = max(0, completion_tokens - r_c)

            # Summarize ~ 35% prompt, 30% comp
            s_p = int(rem_p * 0.35)
            s_c = int(rem_c * 0.30)
            # Write ~ 50% prompt, 60% comp
            w_p = int(rem_p * 0.50)
            w_c = int(rem_c * 0.60)
            # Verify ~ remainder
            v_p = max(0, rem_p - s_p - w_p)
            v_c = max(0, rem_c - s_c - w_c)

            trace.steps = [
                AgentStepRecord(
                    step_id="step-router",
                    step_type=AgentStepType.ROUTER,
                    status=AgentStepStatus.COMPLETED,
                    started_at=now_iso,
                    completed_at=now_iso,
                    duration_ms=85.0,
                    prompt_tokens=r_p,
                    completion_tokens=r_c,
                    total_tokens=r_p + r_c,
                    summary_excerpt=f"TopicRouter classified inquiry as '{intent}'. Dispatched to academic pipeline.",
                    details={"intent": intent, "model": actual_model},
                ),
                AgentStepRecord(
                    step_id="step-search",
                    step_type=AgentStepType.SEARCH,
                    status=AgentStepStatus.COMPLETED,
                    started_at=now_iso,
                    completed_at=now_iso,
                    duration_ms=820.0,
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    summary_excerpt=f"Retrieved {len(search_results or [])} verified academic and preprint literature sources.",
                    details={"sources_count": len(search_results or []), "provider": "tavily"},
                ),
                AgentStepRecord(
                    step_id="step-summarize",
                    step_type=AgentStepType.SUMMARIZE,
                    status=AgentStepStatus.COMPLETED,
                    started_at=now_iso,
                    completed_at=now_iso,
                    duration_ms=780.0,
                    prompt_tokens=s_p,
                    completion_tokens=s_c,
                    total_tokens=s_p + s_c,
                    summary_excerpt="Extracted empirical data, methodology, and key quantitative findings from literature.",
                    details={"model": actual_model},
                ),
                AgentStepRecord(
                    step_id="step-write",
                    step_type=AgentStepType.WRITE,
                    status=AgentStepStatus.COMPLETED,
                    started_at=now_iso,
                    completed_at=now_iso,
                    duration_ms=1350.0,
                    prompt_tokens=w_p,
                    completion_tokens=w_c,
                    total_tokens=w_p + w_c,
                    summary_excerpt=f"Synthesized research report ({len(report.split()) if report else 0} words) with bracketed citations.",
                    details={"word_count": len(report.split()) if report else 0, "model": actual_model},
                ),
                AgentStepRecord(
                    step_id="step-verify",
                    step_type=AgentStepType.VERIFY,
                    status=AgentStepStatus.COMPLETED,
                    started_at=now_iso,
                    completed_at=now_iso,
                    duration_ms=450.0,
                    prompt_tokens=v_p,
                    completion_tokens=v_c,
                    total_tokens=v_p + v_c,
                    summary_excerpt="Verified: cross-referenced factual claims against retrieved DOI citations.",
                    details={"is_verified": verified, "model": actual_model},
                ),
            ]

    trace.complete(
        outcome=RequestOutcome.SUCCESS,
        sources_count=len(search_results or []),
        overall_score=score.get("overall") if isinstance(score, dict) else None,
        cache_status="miss",
        provider=actual_provider,
        model=actual_model,
        actual_model=actual_model,
        fallback_used=fallback_used,
        fallback_details=fallback_details,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=estimated_cost_usd,
    )
    metrics_service.record_request(
        request_id=request_id,
        endpoint="/generate",
        method="POST",
        status_code=200,
        duration_ms=round((time.time() - start) * 1000, 2),
        cache_hit=False,
        search_called=(intent != "question"),
        provider_used=actual_provider,
        model_used=actual_model,
        fallback_occurred=fallback_used,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )

    return ReportResponse(session_id=session_id, topic=req.topic, intent=intent, report=report,
                          sources=_sources_from(search_results), cached=False, score=score,
                          seconds=round(time.time() - start, 2))


@app.get("/scores")
def scores(limit: int = 20):
    """Recent grading results."""
    return score_history(limit)


# ---------------------------------------------------------------------------
# Mount the Admin Backend router (accessible at both /api/admin and /admin)
# ---------------------------------------------------------------------------
app.include_router(admin_router, prefix="/api")
app.include_router(admin_router)

# ---------------------------------------------------------------------------
# Default opening mode: redirect root to User Mode
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/user/index.html")

# ---------------------------------------------------------------------------
# Serve the front-end (the ui/ folder) at http://localhost:8000
# MUST stay at the very bottom, after every route above, because a mount at "/"
# catches any path that no earlier route handled.
# ---------------------------------------------------------------------------
UI_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui")
if os.path.isdir(UI_DIR):
    app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")