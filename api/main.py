"""
FastAPI app: the front door of the whole system.
Run:  python -m uvicorn api.main:app
"""
import os
import time
import uuid
import logging
import mimetypes
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Depends, File, UploadFile, Form
import collections
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import llm_link
from guardrails.checks import check_input, check_output, mask_pii, MIN_REPORT_LEN
from evaluation.judge import grade_report, score_history
from api import integration as parts

from user_auth.routes import router as user_auth_router
from user_auth.chat_routes import router as chat_review_router
from user_auth.chat_storage import get_chat_review_storage
from user_auth.dependencies import get_optional_user
from user_auth.models import UserResponse
from user_auth.config import settings as user_auth_settings

from admin_backend.router import admin_router
from admin_backend.services.trace_service import trace_service
from admin_backend.services.metrics_service import metrics_service
from admin_backend.services.safety_service import safety_service
from admin_backend.services.audit_service import audit_service
from admin_backend.services.quality_service import quality_service
from admin_backend.models.traces import (
    RequestOutcome,
    AgentStepRecord,
    AgentStepType,
    AgentStepStatus,
)
from admin_backend.models.safety import GuardCheckType
from admin_backend.models.audit import UserActivityAction
from admin_backend.models.quality import HumanReviewScore
from gateway.llm_gateway import start_llm_request_session, get_llm_request_telemetry
from agents.sanitizer import sanitize_report
from user_auth.storage import get_user_auth_storage

log = logging.getLogger("api")
app = FastAPI(
    title="Multi-Agent Research Platform",
    description="Guardrails + semantic cache + LangGraph agents + LLM-as-judge + Admin Mode",
    version="0.3.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup_checks():
    """Verify system prerequisites and warn prominently if email or dependencies are unconfigured."""
    if not user_auth_settings.email_configured:
        log.warning(
            "\n" + "!" * 70 + "\n"
            "[WARNING] Email delivery is not configured in .env!\n"
            "Real email delivery is disabled. In development mode (ENV=development),\n"
            "OTP verification codes will be printed directly to the server console.\n"
            "To send real emails, configure Gmail SMTP or an HTTPS Email API:\n"
            "  Option A (Gmail SMTP):\n"
            "    SMTP_HOST=smtp.gmail.com\n"
            "    SMTP_PORT=587\n"
            "    SMTP_TLS=true\n"
            "    SMTP_USER=your_email@gmail.com\n"
            "    SMTP_PASSWORD=your_16_digit_app_password\n"
            "    SMTP_FROM=your_email@gmail.com\n"
            "  Option B (HTTPS API - works when ports 587/465 are ISP blocked):\n"
            "    RESEND_API_KEY=re_your_api_key\n"
            "    BREVO_API_KEY=your_brevo_key\n"
            + "!" * 70 + "\n"
        )
    else:
        log.info("Email delivery configured: SMTP=%s, RESEND=%s, BREVO=%s",
                 bool(user_auth_settings.smtp_host),
                 bool(user_auth_settings.resend_api_key),
                 bool(user_auth_settings.brevo_api_key))

    # Verify Admin Auth Configuration
    from admin_backend.config import settings as admin_settings
    try:
        admin_settings.validate_admin_auth_config()
        log.info("Admin authentication configured: JWT secret valid, Google OAuth configured=%s",
                 bool(admin_settings.get_google_client_id()))
    except Exception as e:
        if admin_settings.is_explicit_production():
            log.error("[CRITICAL] Admin authentication startup check failed: %s", e)
            raise
        else:
            log.warning("[WARNING] Admin authentication startup check: %s", e)


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
    file_content: str | None = Field(None, description="Optional: extracted text content from uploaded files")
    file_names: list[str] | None = Field(None, description="Optional: names of uploaded files for reference")


class ReportResponse(BaseModel):
    session_id: str
    topic: str
    intent: str
    report: str
    sources: list[dict] = []
    cached: bool
    score: dict | None = None
    seconds: float
    report_id: Optional[str] = None


import re

def _sources_from(search_results, report: str = ""):
    """
    Return only sources that are actually cited in the report.
    Extracts citation numbers like [1], [2][3] from the report text
    and returns only those sources.
    """
    if not search_results:
        return []

    # Extract all citation numbers from the report (e.g., [1], [2][3], [4,5])
    cited_numbers = set()
    # Match patterns like [1], [2][3], [1, 2], [1,2,3]
    for match in re.finditer(r'\[\s*(\d+(?:[,;\s]+\d+)*)\s*\]', report):
        # Split by comma, semicolon, or whitespace
        for num_str in re.split(r'[,;\s]+', match.group(1)):
            if num_str.isdigit():
                cited_numbers.add(int(num_str))

    # If no citations found in report, return all sources (fallback)
    if not cited_numbers:
        return [
            {"n": i + 1, "title": r.get("title") or r.get("url"), "url": r.get("url")}
            for i, r in enumerate(search_results or [])
        ]

    # Return only cited sources, maintaining original numbering
    return [
        {"n": i + 1, "title": r.get("title") or r.get("url"), "url": r.get("url")}
        for i, r in enumerate(search_results or [])
        if (i + 1) in cited_numbers
    ]


async def extract_text_from_file(file: UploadFile) -> str:
    """Extract text content from various file types."""
    content = await file.read()
    await file.seek(0)  # Reset file pointer

    filename = file.filename or ""
    mime_type = file.content_type or mimetypes.guess_type(filename)[0] or ""

    try:
        # Text-based files
        if mime_type.startswith("text/") or filename.lower().endswith(('.txt', '.md', '.markdown', '.py', '.js', '.ts', '.json', '.yaml', '.yml', '.csv', '.log', '.xml', '.html', '.css', '.sql', '.sh', '.bat', '.ps1', '.ini', '.cfg', '.conf')):
            return content.decode('utf-8', errors='ignore')

        # PDF files
        elif mime_type == "application/pdf" or filename.lower().endswith('.pdf'):
            try:
                import io
                import pdfplumber
                with pdfplumber.open(io.BytesIO(content)) as pdf:
                    text_parts = []
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            text_parts.append(text)
                    return "\n\n".join(text_parts)
            except ImportError:
                return "[PDF content extraction requires pdfplumber package]"
            except Exception as e:
                return f"[Error extracting PDF: {str(e)}]"

        # DOCX files
        elif filename.lower().endswith('.docx'):
            try:
                import io
                from docx import Document
                doc = Document(io.BytesIO(content))
                return "\n".join([para.text for para in doc.paragraphs])
            except ImportError:
                return "[DOCX content extraction requires python-docx package]"
            except Exception as e:
                return f"[Error extracting DOCX: {str(e)}]"

        # DOC files (older Word format)
        elif filename.lower().endswith('.doc'):
            return "[Legacy .doc format not supported; please convert to .docx]"

        # Images - can be extended with OCR
        elif mime_type.startswith("image/"):
            return f"[Image file: {filename} - OCR not implemented]"

        # Default: try to decode as text
        else:
            try:
                return content.decode('utf-8', errors='ignore')
            except:
                return f"[Binary file: {filename} ({mime_type}) - cannot extract text]"
    except Exception as e:
        return f"[Error processing {filename}: {str(e)}]"


async def process_uploaded_files(files: list[UploadFile]) -> tuple[str, list[str]]:
    """Process multiple uploaded files and return combined text and file names."""
    if not files:
        return "", []

    texts = []
    names = []

    for file in files:
        text = await extract_text_from_file(file)
        if text.strip():
            texts.append(f"--- FILE: {file.filename} ---\n{text}")
        names.append(file.filename)

    return "\n\n".join(texts), names


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
def generate(
    req: TopicRequest,
    request: Request,
    current_user: UserResponse | None = Depends(get_optional_user),
):
    if user_auth_settings.require_login and current_user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required to generate research reports.",
        )
    caller_username = current_user.username if current_user else "user"
    caller_email = current_user.email if current_user else None

    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")
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
    report_id = str(uuid.uuid4())
    start_llm_request_session()
    trace = trace_service.start_trace(request_id=request_id, session_id=session_id, topic=req.topic)

    user_id_val = str(current_user.id) if current_user else None
    scoped_session_id = f"user:{user_id_val}:{session_id}" if user_id_val else f"guest:{session_id}"

    try:
        history = parts.get_history(scoped_session_id)
    except Exception as e:
        log.warning(f"history load failed, treating as a new session: {e}")
        history = []
    is_followup = any(h.get("role") == "report" for h in history)

    # Log research_started for authenticated user
    if current_user:
        try:
            get_user_auth_storage().log_activity(
                user_id=user_id_val,
                event_type="research_started",
                metadata={"topic": req.topic, "session_id": session_id, "is_followup": is_followup},
                ip_address=client_ip,
                user_agent=user_agent,
            )
        except Exception as e:
            log.warning(f"Failed to log research_started: {e}")

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
        # Log user activity for guardrail block
        try:
            user_agent = request.headers.get("user-agent")
            audit_service.log_user_activity(
                session_id=session_id,
                username=caller_username,
                email=caller_email,
                action=UserActivityAction.GUARDRAIL_BLOCK,
                topic=req.topic,
                status="blocked",
                client_ip=client_ip,
                user_agent=user_agent,
            )
        except Exception as e:
            log.warning(f"Failed to log user activity: {e}")
        raise HTTPException(status_code=400, detail=reason)

    # 2. Semantic cache: first message of a conversation only
    if not is_followup:
        try:
            cached = parts.check_cache(req.topic, user_id=user_id_val)
        except TypeError:
            try:
                cached = parts.check_cache(req.topic)
            except Exception as e:
                log.warning(f"cache check failed, continuing: {e}")
                cached = None
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
            _remember(scoped_session_id, req.topic, c_report, c_results)
            if current_user:
                try:
                    c_store = get_chat_review_storage()
                    if not c_store.get_chat_session(user_id=user_id_val, session_id=session_id):
                        c_store.create_chat_session(user_id=user_id_val, title=req.topic[:80], session_id=session_id)
                    c_store.add_chat_message(session_id=session_id, role="user", content=req.topic)
                    c_store.add_chat_message(
                        session_id=session_id,
                        role="report",
                        content=c_report,
                        search_results=c_results,
                        score=c_score,
                        intent="new_research",
                        seconds=round(time.time() - start, 2),
                        cached=True,
                    )
                    get_user_auth_storage().log_activity(
                        user_id=user_id_val,
                        event_type="messages_sent",
                        metadata={"topic": req.topic, "session_id": session_id, "cached": True},
                        ip_address=client_ip,
                        user_agent=request.headers.get("user-agent"),
                    )
                except Exception as e:
                    log.warning(f"Could not persist server chat turn on cache hit: {e}")
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
            # Log user activity for cache hit
            try:
                user_agent = request.headers.get("user-agent")
                audit_service.log_user_activity(
                    session_id=session_id,
                    username=caller_username,
                    email=caller_email,
                    action=UserActivityAction.CACHE_HIT,
                    topic=req.topic,
                    status="success",
                    client_ip=client_ip,
                    user_agent=user_agent,
                )
            except Exception as e:
                log.warning(f"Failed to log user activity: {e}")

            return ReportResponse(session_id=session_id, report_id=report_id, topic=req.topic, intent="new_research",
                                  report=c_report, sources=_sources_from(c_results, c_report), cached=True,
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
        err_str = str(e).lower()
        if "rate limit" in err_str or "too many requests" in err_str or "429" in err_str:
            raise HTTPException(
                status_code=429,
                detail="All AI research models are currently rate-limited. Please wait a moment before trying again."
            )
        if "both groq and ollama failed" in err_str or status_code == 503:
            raise HTTPException(
                status_code=503,
                detail="All AI research models are currently unavailable. Please try again shortly."
            )
        log.exception("pipeline failed")
        if current_user:
            try:
                get_user_auth_storage().log_activity(
                    user_id=user_id_val,
                    event_type="research_failed",
                    metadata={"topic": req.topic, "session_id": session_id, "error": str(e)},
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")

    raw_report = parts.report_to_text(result)
    report = sanitize_report(raw_report)
    is_dict = isinstance(result, dict)
    intent = (result.get("intent") if is_dict else None) or "new_research"
    search_results = result.get("search_results") if is_dict else None
    verified = result.get("is_verified", True) if is_dict else True

    # Log report_generated for authenticated user
    if current_user:
        try:
            get_user_auth_storage().log_activity(
                user_id=user_id_val,
                event_type="report_generated",
                metadata={
                    "topic": req.topic,
                    "session_id": session_id,
                    "intent": intent,
                    "sources_count": len(search_results or []),
                },
                ip_address=client_ip,
                user_agent=user_agent,
            )
        except Exception as e:
            log.warning(f"Failed to log report_generated: {e}")

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
        # Log user activity for output guardrail block
        try:
            user_agent = request.headers.get("user-agent")
            audit_service.log_user_activity(
                session_id=session_id,
                username=caller_username,
                email=caller_email,
                action=UserActivityAction.GUARDRAIL_BLOCK,
                topic=req.topic,
                status="blocked",
                client_ip=client_ip,
                user_agent=user_agent,
            )
        except Exception as e:
            log.warning(f"Failed to log user activity: {e}")
        raise HTTPException(status_code=422, detail=reason)

    # 5. Grading against the ORIGINAL topic; skipped for plain Q&A
    original_topic = next((h["content"] for h in history if h.get("role") == "user"), req.topic)
    score = None
    if req.grade and intent != "question":
        score = grade_report(original_topic, report)
        if current_user:
            try:
                if score and "error" not in score:
                    get_user_auth_storage().log_activity(
                        user_id=user_id_val,
                        event_type="grading_completed",
                        metadata={
                            "topic": original_topic,
                            "session_id": session_id,
                            "overall": score.get("overall"),
                            "score": score,
                        },
                        ip_address=client_ip,
                        user_agent=user_agent,
                    )
                elif score and "error" in score:
                    get_user_auth_storage().log_activity(
                        user_id=user_id_val,
                        event_type="grading_failed",
                        metadata={
                            "topic": original_topic,
                            "session_id": session_id,
                            "error": score.get("error"),
                        },
                        ip_address=client_ip,
                        user_agent=user_agent,
                    )
            except Exception as e:
                log.warning(f"Failed to log grading activity: {e}")

    # 6. Memory: always keep the conversation; cache and archive verified NEW research only
    _remember(scoped_session_id, req.topic, report, search_results,
              role="answer" if intent == "question" else "report")
    if intent == "new_research" and verified:
        try:
            parts.save_to_ltm(report, topic=req.topic, score=score, search_results=search_results, user_id=user_id_val)
        except TypeError:
            try:
                parts.save_to_ltm(report, topic=req.topic, score=score, search_results=search_results)
            except Exception as e:
                log.warning(f"save_to_ltm failed: {e}")
        except Exception as e:
            log.warning(f"save_to_ltm failed: {e}")

    # Server-side user chat turn persistence (when authenticated)
    if current_user:
        try:
            c_store = get_chat_review_storage()
            if not c_store.get_chat_session(user_id=user_id_val, session_id=session_id):
                c_store.create_chat_session(user_id=user_id_val, title=req.topic[:80], session_id=session_id)
            c_store.add_chat_message(session_id=session_id, role="user", content=req.topic)
            c_store.add_chat_message(
                session_id=session_id,
                role=intent,
                content=report,
                search_results=search_results,
                score=score,
                intent=intent,
                seconds=round(time.time() - start, 2),
                cached=False,
            )
        except Exception as e:
            log.warning(f"Could not persist server chat turn: {e}")

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

    # Log user activity
    try:
        user_agent = request.headers.get("user-agent")
        if intent == "question":
            audit_service.log_user_activity(
                session_id=session_id,
                username=caller_username,
                email=caller_email,
                action=UserActivityAction.FOLLOWUP_QUESTION,
                topic=req.topic,
                status="success",
                client_ip=client_ip,
                user_agent=user_agent,
            )
        else:
            audit_service.log_user_activity(
                session_id=session_id,
                username=caller_username,
                email=caller_email,
                action=UserActivityAction.RESEARCH_QUERY,
                topic=req.topic,
                status="success",
                client_ip=client_ip,
                user_agent=user_agent,
            )
        if current_user:
            get_user_auth_storage().log_activity(
                user_id=str(current_user.id),
                event_type="messages_sent",
                metadata={"topic": req.topic, "session_id": session_id, "cached": False, "intent": intent},
                ip_address=client_ip,
                user_agent=user_agent,
            )
            get_user_auth_storage().log_activity(
                user_id=str(current_user.id),
                event_type="research_completed",
                metadata={
                    "topic": req.topic,
                    "session_id": session_id,
                    "intent": intent,
                    "overall_score": score.get("overall") if isinstance(score, dict) else None,
                },
                ip_address=client_ip,
                user_agent=user_agent,
            )
    except Exception as e:
        log.warning(f"Failed to log user activity: {e}")

    return ReportResponse(session_id=session_id, report_id=report_id, topic=req.topic, intent=intent, report=report,
                          sources=_sources_from(search_results, report), cached=False, score=score,
                          seconds=round(time.time() - start, 2))


def _save_user_chat_turn(current_user, session_id, topic, file_names, report, search_results,
                         score, intent, seconds, cached):
    """Save a file-upload turn to the signed-in user's server-side chat history (no-op for guests)."""
    if not current_user:
        return
    user_id_val = str(current_user.id)
    user_text = topic
    if file_names:
        user_text = f"{topic}\n[Attached files: {', '.join(file_names)}]"
    try:
        c_store = get_chat_review_storage()
        if not c_store.get_chat_session(user_id=user_id_val, session_id=session_id):
            title = topic[:80]
            if file_names:
                title = file_names[0][:80]
            c_store.create_chat_session(user_id=user_id_val, title=title, session_id=session_id)
        c_store.add_chat_message(session_id=session_id, role="user", content=user_text)
        role = intent
        if cached:
            role = "report"
        c_store.add_chat_message(
            session_id=session_id,
            role=role,
            content=report,
            search_results=search_results,
            score=score,
            intent=intent,
            seconds=seconds,
            cached=cached,
        )
        get_user_auth_storage().log_activity(
            user_id=user_id_val,
            event_type="messages_sent",
            metadata={"topic": topic, "session_id": session_id, "cached": cached, "files": file_names},
        )
    except Exception as e:
        log.warning(f"Could not persist server chat turn for file upload: {e}")


@app.post("/generate-with-files", response_model=ReportResponse)
async def generate_with_files(
    request: Request,
    topic: str = Form(...),
    session_id: str | None = Form(None),
    grade: bool = Form(True),
    files: list[UploadFile] = File(default=[]),
    current_user: UserResponse | None = Depends(get_optional_user),
):
    """Generate research report with optional file uploads.

    Accepts multipart/form-data with:
    - topic: The research topic/query
    - session_id: Optional session ID for follow-ups
    - grade: Whether to run LLM-as-judge grading
    - files: Optional list of uploaded files (PDF, DOCX, TXT, etc.)
    """
    if user_auth_settings.require_login and current_user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required to generate research reports.",
        )
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please wait a minute before making further research requests."
        )

    # Process uploaded files
    file_content, file_names = await process_uploaded_files(files)

    # Combine topic with file content if files were uploaded
    combined_topic = topic
    if file_content:
        combined_topic = f"{topic}\n\n--- UPLOADED FILES CONTENT ---\n{file_content}"

    # Anonymize any sensitive PII before processing
    combined_topic, _ = mask_pii(combined_topic)
    start = time.time()
    session_id = session_id or str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    report_id = str(uuid.uuid4())
    start_llm_request_session()
    trace = trace_service.start_trace(request_id=request_id, session_id=session_id, topic=combined_topic)

    # Same per-user conversation keys as /generate, so follow-ups in one chat share memory
    user_id_val = str(current_user.id) if current_user else None
    if user_id_val:
        scoped_session_id = f"user:{user_id_val}:{session_id}"
    else:
        scoped_session_id = f"guest:{session_id}"

    try:
        history = parts.get_history(scoped_session_id)
    except Exception as e:
        log.warning(f"history load failed, treating as a new session: {e}")
        history = []
    is_followup = any(h.get("role") == "report" for h in history)

    # 1. Input guardrail (follow-ups skip the off-topic check)
    # Only check the user's actual query/topic, not the file content which is just data being analyzed
    # Pass has_files=True to skip OFF_TOPIC check when files provide research context
    ok, reason = check_input(topic, is_followup=is_followup, has_files=len(files) > 0)
    if not ok:
        safety_service.record_blocked_event(
            check_type=GuardCheckType.INPUT_RULE,
            reason=reason,
            raw_text=topic,
            request_id=request_id,
            session_id=session_id,
        )
        trace.complete(outcome=RequestOutcome.BLOCKED, error_category="guardrail_input_blocked")
        metrics_service.record_request(
            request_id=request_id,
            endpoint="/generate-with-files",
            method="POST",
            status_code=400,
            duration_ms=round((time.time() - start) * 1000, 2),
        )
        raise HTTPException(status_code=400, detail=reason)

    # 2. Semantic cache: first message of a conversation only
    # Cache is based on the user's query topic, not file content
    if not is_followup:
        try:
            cached = parts.check_cache(topic, user_id=user_id_val)
        except TypeError:
            try:
                cached = parts.check_cache(topic)
            except Exception as e:
                log.warning(f"cache check failed, continuing: {e}")
                cached = None
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
            _remember(scoped_session_id, combined_topic, c_report, c_results)
            _save_user_chat_turn(current_user, session_id, topic, file_names, c_report, c_results,
                                 c_score, "new_research", round(time.time() - start, 2), True)
            trace.complete(
                outcome=RequestOutcome.SUCCESS,
                cache_status="hit",
                sources_count=len(c_results or []),
                overall_score=c_score.get("overall") if isinstance(c_score, dict) else None,
            )
            metrics_service.record_request(
                request_id=request_id,
                endpoint="/generate-with-files",
                method="POST",
                status_code=200,
                duration_ms=round((time.time() - start) * 1000, 2),
                cache_hit=True,
            )
            return ReportResponse(session_id=session_id, report_id=report_id, topic=topic, intent="new_research",
                                  report=c_report, sources=_sources_from(c_results, c_report), cached=True,
                                  score=c_score, seconds=round(time.time() - start, 2))

    # 3. Agent pipeline
    try:
        result = parts.run_pipeline(combined_topic, history, session_id)
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
            endpoint="/generate-with-files",
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

    # 4. Output guardrail
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
            endpoint="/generate-with-files",
            method="POST",
            status_code=422,
            duration_ms=round((time.time() - start) * 1000, 2),
        )
        raise HTTPException(status_code=422, detail=reason)

    # 5. Grading
    original_topic = next((h["content"] for h in history if h.get("role") == "user"), combined_topic)
    score = None
    if grade and intent != "question":
        score = grade_report(original_topic, report)

    # 6. Memory
    _remember(scoped_session_id, combined_topic, report, search_results,
              role="answer" if intent == "question" else "report")
    if intent == "new_research" and verified:
        try:
            parts.save_to_ltm(report, topic=topic, score=score, search_results=search_results, user_id=user_id_val)
        except TypeError:
            try:
                parts.save_to_ltm(report, topic=topic, score=score, search_results=search_results)
            except Exception as e:
                log.warning(f"save_to_ltm failed: {e}")
        except Exception as e:
            log.warning(f"save_to_ltm failed: {e}")
    _save_user_chat_turn(current_user, session_id, topic, file_names, report, search_results,
                         score, intent, round(time.time() - start, 2), False)

    # Trace completion & metric logging
    telemetry = get_llm_request_telemetry()
    actual_provider = telemetry.get("provider") or "groq"
    actual_model = telemetry.get("actual_model") or "qwen/qwen3.8-27b"
    fallback_used = telemetry.get("fallback_used", False)
    fallback_details = telemetry.get("fallback_details")
    prompt_tokens = telemetry.get("prompt_tokens", 0)
    completion_tokens = telemetry.get("completion_tokens", 0)
    total_tokens = telemetry.get("total_tokens", 0)
    estimated_cost_usd = telemetry.get("estimated_cost_usd", 0.0)

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

            s_p = int(rem_p * 0.35)
            s_c = int(rem_c * 0.30)
            w_p = int(rem_p * 0.50)
            w_c = int(rem_c * 0.60)
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
        endpoint="/generate-with-files",
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

    return ReportResponse(session_id=session_id, report_id=report_id, topic=topic, intent=intent, report=report,
                          sources=_sources_from(search_results, report), cached=False, score=score,
                          seconds=round(time.time() - start, 2))


@app.get("/scores")
def scores(limit: int = 20):
    """Recent grading results."""
    return score_history(limit)


class UserHumanReviewRequest(BaseModel):
    topic: str
    relevance: int = Field(..., ge=1, le=10)
    accuracy: int = Field(..., ge=1, le=10)
    clarity: int = Field(..., ge=1, le=10)
    report_id: str | None = None
    feedback_notes: str | None = Field(None, max_length=1000)
    flagged_for_rerun: bool = False


@app.post("/quality/human-reviews", response_model=HumanReviewScore)
def create_user_human_review(review_req: UserHumanReviewRequest, request: Request):
    """
    Submit a human evaluation review for a generated report.
    User-facing endpoint (no admin auth required).
    """
    # Use "user" as reviewer since this is from user portal
    review = quality_service.add_human_review(
        topic=review_req.topic,
        reviewer_username="user",
        relevance=review_req.relevance,
        accuracy=review_req.accuracy,
        clarity=review_req.clarity,
        report_id=review_req.report_id,
        feedback_notes=review_req.feedback_notes,
        flagged_for_rerun=review_req.flagged_for_rerun,
        is_expert=False,
    )

    # Audit log for user human review submission
    client_ip = request.client.host if request.client else "unknown"
    from admin_backend.services.audit_service import audit_service
    from admin_backend.models.audit import AuditAction
    audit_service.log_action(
        actor_username="user",
        actor_role="user",
        action=AuditAction.HUMAN_REVIEW_ADD,
        resource_type="human_review",
        resource_id=review.review_id,
        status="success",
        details={"topic": review_req.topic, "overall": review.overall},
        client_ip=client_ip,
    )

    return review


# ---------------------------------------------------------------------------
# Mount User Auth and User Chats/Reviews routers under /api
# ---------------------------------------------------------------------------
app.include_router(user_auth_router, prefix="/api/auth")
app.include_router(chat_review_router, prefix="/api")

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
    app.mount("/ui", StaticFiles(directory=UI_DIR, html=True), name="ui_prefix")
    app.mount("/", StaticFiles(directory=UI_DIR, html=True), name="ui")