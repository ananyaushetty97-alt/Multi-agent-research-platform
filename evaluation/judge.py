"""
Grading: "LLM-as-a-judge", tracked in LangSmith.

After the Write agent finishes, a second LLM call reads the report and scores it.

    result = grade_report(topic, report)
    # {"relevance": 8, "accuracy": 7, "clarity": 9, "overall": 8.0, "comment": "..."}

Where the scores go:
  1. Returned to the API (shown in the UI).
  2. Appended to logs/scores.jsonl, together with the judge's RAW reply, so
     anyone can check the numbers really came from the LLM.
  3. LangSmith (only if LANGSMITH_TRACING=true and LANGSMITH_API_KEY are set):
     every judge call is recorded as a run called "llm_judge", with the prompt,
     the raw reply and the parsed scores, and each score is attached as
     "feedback" (relevance / accuracy / clarity / overall) so you can filter,
     chart and compare runs in the LangSmith dashboard.

If LangSmith isn't installed or configured, everything still works; the
LangSmith parts just switch themselves off.

Known weakness (say this before the examiner does): the judge can be biased,
especially when the same model both writes and judges. Fixes: use a different
model as judge, use a rubric, or compare with human ratings.
evaluation/check_judge_real.py tests whether the scores behave like real
judgements (good reports score higher than bad ones, repeat scores agree).
"""
import os
import re
import json
import time
import logging

log = logging.getLogger("evaluation")
LOG_PATH = os.getenv("SCORES_LOG", os.path.join("logs", "scores.jsonl"))
CRITERIA = ("relevance", "accuracy", "clarity")

JUDGE_PROMPT = """You are a strict examiner grading a research report.

Score each criterion from 1 (very poor) to 10 (excellent):
- relevance: does it answer the topic "{topic}"?
- accuracy: are the claims factually correct and not made up?
- clarity: is it well-structured and easy to read?

Return ONLY a JSON object, no other text:
{{"relevance": <int>, "accuracy": <int>, "clarity": <int>, "comment": "<one sentence>"}}

REPORT:
{report}"""


# --- LangSmith (optional) ----------------------------------------------------
try:
    from langsmith import traceable
    from langsmith.run_helpers import get_current_run_tree
except ImportError:  # langsmith not installed: tracing becomes a no-op
    def traceable(*dargs, **dkwargs):
        if dargs and callable(dargs[0]) and not dkwargs:
            return dargs[0]
        return lambda fn: fn

    def get_current_run_tree():
        return None


def langsmith_enabled() -> bool:
    flag = (os.getenv("LANGSMITH_TRACING") or os.getenv("LANGCHAIN_TRACING_V2") or "").lower()
    key = os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
    return flag == "true" and bool(key)


_client = None


def _ls_client():
    global _client
    if _client is None:
        from langsmith import Client
        _client = Client()
    return _client


def _send_feedback(run_id, scores: dict) -> None:
    """Attach each score to the judge run in LangSmith, so the dashboard can chart them."""
    if run_id is None or not langsmith_enabled():
        return
    try:
        client = _ls_client()
        for key in (*CRITERIA, "overall"):
            if key in scores:
                client.create_feedback(
                    run_id=run_id,
                    key=key,
                    score=scores[key] / 10,          # LangSmith charts work best on 0–1
                    value=scores[key],               # the original 1–10 score
                    comment=scores.get("comment") if key == "overall" else None,
                )
    except Exception as e:  # never let monitoring break grading
        log.warning(f"LangSmith feedback not sent: {e}")


# --- Helpers -------------------------------------------------------------------
def _extract_json(text: str) -> dict:
    """LLMs often wrap JSON in ```json fences or add chatter. Pull out the {...}."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON found in judge output: {text[:200]}")
    return json.loads(match.group(0))


def _clamp(value) -> int:
    return max(1, min(10, int(round(float(value)))))


def _log(entry: dict) -> None:
    try:
        os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        log.warning(f"Could not write score log: {e}")


# --- Main ----------------------------------------------------------------------
@traceable(name="llm_judge", run_type="chain", tags=["judge"])
def grade_report(topic: str, report: str, llm=None) -> dict:
    if llm is None:
        from llm_link import call_llm as llm

    prompt = JUDGE_PROMPT.format(topic=topic, report=report[:6000])
    result, raw_text, last_error = None, None, None
    attempts = 0
    for attempt in range(2):  # one retry, because JSON output is flaky
        attempts += 1
        try:
            raw_text = llm(prompt)
            raw = _extract_json(raw_text)
            scores = {c: _clamp(raw[c]) for c in CRITERIA}
            scores["overall"] = round(sum(scores.values()) / len(CRITERIA), 1)
            scores["comment"] = str(raw.get("comment", ""))[:300]
            result = scores
            break
        except Exception as e:
            last_error = e
            log.warning(f"Judge attempt {attempt + 1} failed: {e}")

    if result is None:
        result = {"error": f"grading failed: {last_error}"}

    run = get_current_run_tree()
    run_id = getattr(run, "id", None)
    if run is not None:
        try:  # makes judge runs searchable by topic in LangSmith
            run.metadata.update({"topic": topic[:200], "judge_attempts": attempts})
        except Exception:
            pass
    if "error" not in result:
        _send_feedback(run_id, result)

    _log({
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "topic": topic,
        **result,
        "raw_judge_output": (raw_text or "")[:1000],   # proof the numbers came from the LLM
        "langsmith_run_id": str(run_id) if run_id else None,
    })
    return result


def score_history(limit: int = 20) -> list[dict]:
    """Last N grading results, newest first (used by GET /scores)."""
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH) as f:
        lines = f.readlines()[-limit:]
    return [json.loads(line) for line in reversed(lines) if line.strip()]
