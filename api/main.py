"""
FastAPI app — the front door of the whole system.

Run locally:   uvicorn api.main:app --reload
Test UI:       http://localhost:8000/docs

Request flow for POST /generate:
  input guardrail -> cache check (B) -> pipeline (A) -> output guardrail
  -> grading (C) -> save to long-term memory (B) -> response
"""
import time
import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

import llm_link
from guardrails.checks import check_input, check_output
from evaluation.judge import grade_report, score_history
from api import integration as parts

log = logging.getLogger("api")
app = FastAPI(
    title="Multi-Agent Research Platform",
    description="Guardrails + semantic cache + LangGraph agents + LLM-as-judge",
    version="0.1.0",
)


class TopicRequest(BaseModel):
    topic: str = Field(..., examples=["Impact of large language models on healthcare"])
    grade: bool = Field(True, description="Run the LLM-as-judge after generating")


class ReportResponse(BaseModel):
    topic: str
    report: str
    cached: bool
    score: dict | None = None
    seconds: float


@app.get("/health")
def health():
    """Shows which parts are connected (real) vs stubbed."""
    _, gateway_name = llm_link.find_call_llm()
    return {
        "status": "ok",
        "gateway": gateway_name or "NOT FOUND",
        "pipeline": "stub" if parts.PIPELINE_IS_STUB else "real",
        "cache": "stub" if parts.CACHE_IS_STUB else "real",
        "ltm": "stub" if parts.LTM_IS_STUB else "real",
    }


@app.post("/generate", response_model=ReportResponse)
def generate(req: TopicRequest):
    start = time.time()

    # 1. Input guardrail
    ok, reason = check_input(req.topic)
    if not ok:
        raise HTTPException(status_code=400, detail=reason)

    # 2. Semantic cache (Person B) — a failure here must not break the request
    try:
        cached = parts.check_cache(req.topic)
    except Exception as e:
        log.warning(f"cache check failed, continuing: {e}")
        cached = None
    if cached:
        if isinstance(cached, dict) and "report" in cached:
            cached_report = cached["report"]
            cached_score = cached.get("score")
        else:
            cached_report = parts.report_to_text(cached)
            cached_score = None
        return ReportResponse(topic=req.topic, report=cached_report,
                          cached=True, score=cached_score, seconds=round(time.time() - start, 2))
    # 3. Agent pipeline (Person A)
    try:
        report = parts.report_to_text(parts.run_pipeline(req.topic))
    except Exception as e:
        if "LLMUnavailable" in type(e).__name__ or "No gateway found" in str(e):
            raise HTTPException(status_code=503, detail=f"LLM unavailable: {e}")
        log.exception("pipeline failed")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")

    # 4. Output guardrail
    ok, reason = check_output(report)
    if not ok:
        raise HTTPException(status_code=422, detail=reason)

    # 5. Grading (LLM-as-judge)
    score = grade_report(req.topic, report) if req.grade else None

    # 6. Long-term memory (Person B) — also must not break the request
    try:
        parts.save_to_ltm(report, topic=req.topic, score=score)
    except Exception as e:
        log.warning(f"save_to_ltm failed: {e}")

    return ReportResponse(topic=req.topic, report=report, cached=False,
                          score=score, seconds=round(time.time() - start, 2))


@app.get("/scores")
def scores(limit: int = 20):
    """Recent grading results — the demo's stand-in for a LangSmith dashboard."""
    return score_history(limit)
