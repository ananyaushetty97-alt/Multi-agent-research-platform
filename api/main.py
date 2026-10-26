"""
FastAPI app: the front door of the whole system.
Run:  python -m uvicorn api.main:app
"""
import time
import uuid
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import llm_link
from guardrails.checks import check_input, check_output, MIN_REPORT_LEN
from evaluation.judge import grade_report, score_history
from api import integration as parts

log = logging.getLogger("api")
app = FastAPI(
    title="Multi-Agent Research Platform",
    description="Guardrails + semantic cache + LangGraph agents + LLM-as-judge",
    version="0.3.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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


@app.post("/generate", response_model=ReportResponse)
def generate(req: TopicRequest):
    start = time.time()
    session_id = req.session_id or str(uuid.uuid4())

    try:
        history = parts.get_history(session_id)
    except Exception as e:
        log.warning(f"history load failed, treating as a new session: {e}")
        history = []
    is_followup = any(h.get("role") == "report" for h in history)

    # 1. Input guardrail (follow-ups skip the off-topic check)
    ok, reason = check_input(req.topic, is_followup=is_followup)
    if not ok:
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
            return ReportResponse(session_id=session_id, topic=req.topic, intent="new_research",
                                  report=c_report, sources=_sources_from(c_results), cached=True,
                                  score=c_score, seconds=round(time.time() - start, 2))

    # 3. Agent pipeline (the router inside decides new research / modify / question)
    try:
        result = parts.run_pipeline(req.topic, history, session_id)
    except Exception as e:
        if "LLMUnavailable" in type(e).__name__ or "No gateway found" in str(e):
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

    return ReportResponse(session_id=session_id, topic=req.topic, intent=intent, report=report,
                          sources=_sources_from(search_results), cached=False, score=score,
                          seconds=round(time.time() - start, 2))


@app.get("/scores")
def scores(limit: int = 20):
    """Recent grading results."""
    return score_history(limit)
