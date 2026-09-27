"""
Grading — "LLM-as-a-judge".

After the Write agent finishes, a second LLM call reads the report and scores it.

    result = grade_report(topic, report)
    # {"relevance": 8, "accuracy": 7, "clarity": 9, "overall": 8.0, "comment": "..."}

Every result is appended to logs/scores.jsonl so you can show a score history
in the demo (this replaces the LangSmith dashboard for the 2-day version).

Known weakness (say this before the examiner does): the judge can be biased,
especially when the same model both writes and judges. Fixes: use a different
model as judge, use a rubric, or compare with human ratings.
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


def grade_report(topic: str, report: str, llm=None) -> dict:
    if llm is None:
        from llm_link import call_llm as llm

    prompt = JUDGE_PROMPT.format(topic=topic, report=report[:6000])
    result = None
    last_error = None
    for attempt in range(2):  # one retry, because JSON output is flaky
        try:
            raw = _extract_json(llm(prompt))
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

    _log({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "topic": topic, **result})
    return result


def score_history(limit: int = 20) -> list[dict]:
    """Last N grading results, newest first (used by GET /scores)."""
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH) as f:
        lines = f.readlines()[-limit:]
    return [json.loads(line) for line in reversed(lines) if line.strip()]
