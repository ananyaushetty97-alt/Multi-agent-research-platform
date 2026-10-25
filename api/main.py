"""
FastAPI app: the front door of the whole system.
Run:  python -m uvicorn api.main:app
"""
import time
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import llm_link
from guardrails.checks import check_input, check_output
from evaluation.judge import grade_report, score_history
from api import integration as parts

log = logging.getLogger("api")
app = FastAPI(
    title="Multi-Agent Research Platform",
    description="Guardrails + semantic cache + LangGraph agents + LLM-as-judge",
    version="0.2.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class TopicRequest(BaseModel):
    topic: str = Field(..., examples=["Impact of large language models on healthcare"])
    grade: bool = Field(True, description="Run the LLM-as-judge after generating")


class ReportResponse(BaseModel):
    topic: str
    report: str
    sources: list[dict] = []
    cached: bool
    score: dict | None = None
    seconds: float


def _sources_from(search_results):
    """[{n: 1, title, url}, ...]. The position matches the [N] markers in the report."""
    return [
        {"n": i + 1, "title": r.get("title") or r.get("url"), "url": r.get("url")}
        for i, r in enumerate(search_results or [])
    ]


@app.get("/health")
def health():
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

    # 2. Semantic cache: a failure here must not break the request
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
        return ReportResponse(topic=req.topic, report=c_report, sources=_sources_from(c_results),
                              cached=True, score=c_score, seconds=round(time.time() - start, 2))

    # 3. Agent pipeline
    try:
        result = parts.run_pipeline(req.topic)
    except Exception as e:
        if "LLMUnavailable" in type(e).__name__ or "No gateway found" in str(e):
            raise HTTPException(status_code=503, detail=f"LLM unavailable: {e}")
        log.exception("pipeline failed")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")

    report = parts.report_to_text(result)
    is_dict = isinstance(result, dict)
    search_results = result.get("search_results") if is_dict else None
    verified = result.get("is_verified", True) if is_dict else True

    # 4. Output guardrail
    ok, reason = check_output(report)
    if not ok:
        raise HTTPException(status_code=422, detail=reason)

    # 5. Grading
    score = grade_report(req.topic, report) if req.grade else None

    # 6. Cache + long-term memory: verified reports only
    if verified:
        try:
            parts.save_to_ltm(report, topic=req.topic, score=score, search_results=search_results)
        except Exception as e:
            log.warning(f"save_to_ltm failed: {e}")

    return ReportResponse(topic=req.topic, report=report, sources=_sources_from(search_results),
                          cached=False, score=score, seconds=round(time.time() - start, 2))


@app.get("/scores")
def scores(limit: int = 20):
    """Recent grading results."""
    return score_history(limit)
