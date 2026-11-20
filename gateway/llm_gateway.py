import os
import time
import contextvars
from typing import Dict, List, Any, Optional
from groq import Groq
from ollama import Client as OllamaClient
from dotenv import load_dotenv

load_dotenv()

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
ollama_client = OllamaClient(host="http://localhost:11434")

GROQ_MODEL = "qwen/qwen3.8-27b"      # check console.groq.com/docs/models — Groq renames/deprecates models occasionally
OLLAMA_MODEL = "qwen2.5:7b"          # must match what you pulled with `ollama pull`

# Request-scoped telemetry context variable
_active_request_llm_telemetry: contextvars.ContextVar[Optional[List[Dict[str, Any]]]] = contextvars.ContextVar(
    "_active_request_llm_telemetry", default=None
)


def start_llm_request_session():
    """Initialize a clean LLM telemetry collection buffer for the current request context."""
    _active_request_llm_telemetry.set([])


def record_call_telemetry(data: Dict[str, Any]):
    """Record single LLM invocation telemetry into the active request context."""
    buf = _active_request_llm_telemetry.get()
    if buf is not None:
        buf.append(data)


def get_llm_request_telemetry() -> Dict[str, Any]:
    """
    Summarize LLM execution metadata for the current request:
    - Which model actually executed the work
    - Whether fallback was triggered and from/to which model
    - Total, prompt, and completion token consumption
    - Cost estimation
    """
    calls = _active_request_llm_telemetry.get() or []
    if not calls:
        return {
            "provider": "groq",
            "model": GROQ_MODEL,
            "actual_model": GROQ_MODEL,
            "fallback_used": False,
            "fallback_details": None,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "calls": [],
        }

    total_prompt = sum(c.get("prompt_tokens", 0) for c in calls)
    total_completion = sum(c.get("completion_tokens", 0) for c in calls)
    total_tokens = sum(c.get("total_tokens", 0) for c in calls)
    any_fallback = any(c.get("fallback_used", False) for c in calls)

    # Determine dominant/latest working model
    last_call = calls[-1]
    actual_model = last_call.get("model", GROQ_MODEL)
    actual_provider = last_call.get("provider", "groq")

    fallback_details = None
    if any_fallback:
        reasons = [c.get("fallback_reason") for c in calls if c.get("fallback_reason")]
        fallback_details = f"Groq ({GROQ_MODEL}) failed: {reasons[0] if reasons else 'Unspecified error'} -> Fallback to Ollama ({OLLAMA_MODEL})"

    # Cost estimate (approx $0.05 per 1M tokens on Groq, $0.00 local Ollama)
    cost = 0.0
    for c in calls:
        if c.get("provider") == "groq":
            cost += round((c.get("total_tokens", 0) / 1_000_000) * 0.05, 6)

    return {
        "provider": actual_provider,
        "model": actual_model,
        "actual_model": actual_model,
        "fallback_used": any_fallback,
        "fallback_details": fallback_details,
        "prompt_tokens": total_prompt,
        "completion_tokens": total_completion,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(cost, 6),
        "calls": calls,
    }


def _call_groq(prompt: str, system_prompt: str, max_tokens: Optional[int] = None) -> str:
    start_time = time.perf_counter()
    lower_p = prompt.lower()
    lower_s = system_prompt.lower()
    # Dynamic token budgeting to respect Groq OTPM limits (1000 OTPM on free tier)
    if max_tokens is not None:
        actual_max = max_tokens
    elif "one word" in lower_p or "exactly the word" in lower_p or "classifier" in lower_s:
        actual_max = 30
    elif "fact-checker" in lower_s or "verified" in lower_p:
        actual_max = 150
    elif "summariz" in lower_s or "summarizer" in lower_s:
        actual_max = 350
    elif "judge" in lower_s or "grade" in lower_s:
        actual_max = 200
    elif "editor" in lower_s or "modify" in lower_s or "writer" in lower_s:
        actual_max = 900
    else:
        actual_max = 600

    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        max_tokens=actual_max,
    )
    content = response.choices[0].message.content or ""
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    # Token counting
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None) or max(1, len(prompt) // 4)
    completion_tokens = getattr(usage, "completion_tokens", None) or max(1, len(content) // 4)
    total_tokens = getattr(usage, "total_tokens", None) or (prompt_tokens + completion_tokens)

    record_call_telemetry({
        "provider": "groq",
        "model": GROQ_MODEL,
        "fallback_used": False,
        "fallback_reason": None,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "duration_ms": duration_ms,
    })

    return content


def _call_ollama(prompt: str, system_prompt: str, fallback_reason: Optional[str] = None, max_tokens: Optional[int] = None) -> str:
    start_time = time.perf_counter()
    opts = {"num_predict": max_tokens} if max_tokens else None
    response = ollama_client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        options=opts
    )
    content = response.get("message", {}).get("content", "")
    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

    prompt_tokens = response.get("prompt_eval_count") or max(1, len(prompt) // 4)
    completion_tokens = response.get("eval_count") or max(1, len(content) // 4)
    total_tokens = prompt_tokens + completion_tokens

    record_call_telemetry({
        "provider": "ollama",
        "model": OLLAMA_MODEL,
        "fallback_used": fallback_reason is not None,
        "fallback_reason": fallback_reason,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "duration_ms": duration_ms,
    })

    return content


def call_llm(prompt: str, system_prompt: str = "You are a helpful research assistant.", max_tokens: Optional[int] = None) -> str:
    """
    Every agent calls this. Tries Groq (Qwen, cloud, fast) first.
    Falls back to Ollama (Qwen, local) if Groq fails for any reason
    (rate limit, network issue, outage, bad API key, etc).
    """
    try:
        return _call_groq(prompt, system_prompt, max_tokens=max_tokens)
    except Exception as e:
        err_msg = str(e)
        print(f"[gateway] Groq call failed ({err_msg}), falling back to Ollama...")
        try:
            return _call_ollama(prompt, system_prompt, fallback_reason=err_msg, max_tokens=max_tokens)
        except Exception as e2:
            raise RuntimeError(f"Both Groq and Ollama failed. Groq error: {e}. Ollama error: {e2}")
