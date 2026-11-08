"""
LangSmith evaluation: run the REAL pipeline on a fixed set of topics and score
every report, so results can be compared between versions of the code.

    python -m evaluation.langsmith_eval              # 5 topics, results uploaded to LangSmith
    python -m evaluation.langsmith_eval --topics 2   # quicker run (Groq free-tier friendly)
    python -m evaluation.langsmith_eval --local      # no LangSmith: just print the table

What gets measured for each report:
  relevance / accuracy / clarity / overall   from our LLM judge (evaluation/judge.py)
  citation_validity   share of [N] citations that point to a real source (computed, no LLM)
  has_citations       does the report cite anything at all (computed)
  verified            did the Verify agent pass it (from the pipeline)

The computed metrics don't depend on any LLM, so they double-check the judge:
a report with no valid citations shouldn't get a high accuracy score.

In LangSmith this appears as a Dataset ("research-topics-v1") and one
Experiment per run, where every row shows the topic, the report and all scores.
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

DATASET_NAME = "research-topics-v1"
TOPICS = [
    "Impact of large language models on healthcare diagnostics",
    "Renewable energy adoption in India since 2015",
    "How mRNA vaccines work",
    "Causes and effects of microplastics in oceans",
    "Use of AI in detecting financial fraud",
]

CITE_RE = re.compile(r"\[(\d+)\]")


# --- metrics that don't use an LLM --------------------------------------------
def citation_metrics(report: str, n_sources: int) -> dict:
    from agents.citation_utils import strip_sources

    body = strip_sources(report or "")
    cited = [int(n) for n in CITE_RE.findall(body)]
    if not cited:
        return {"has_citations": 0, "citation_validity": 0.0}
    valid = sum(1 for n in cited if 1 <= n <= n_sources)
    return {"has_citations": 1, "citation_validity": round(valid / len(cited), 2)}


# --- target: the system under test ---------------------------------------------
def run_system(inputs: dict) -> dict:
    """Runs the real LangGraph pipeline for one topic."""
    from graph.pipeline import run_pipeline

    start = time.time()
    state = run_pipeline(inputs["topic"])
    return {
        "report": state.get("report") or "",
        "n_sources": len(state.get("search_results") or []),
        "verified": bool(state.get("is_verified")),
        "revisions": state.get("revision_count", 0),
        "seconds": round(time.time() - start, 1),
    }


# --- evaluator: what LangSmith calls for each row --------------------------------
def score_report(inputs: dict, outputs: dict) -> list[dict]:
    from evaluation.judge import grade_report

    judge = grade_report(inputs["topic"], outputs["report"])
    results = []
    if "error" in judge:
        results.append({"key": "judge_error", "score": 1, "comment": judge["error"]})
    else:
        for key in ("relevance", "accuracy", "clarity", "overall"):
            results.append({"key": key, "score": judge[key] / 10, "value": judge[key],
                            "comment": judge.get("comment") if key == "overall" else None})
    for key, val in citation_metrics(outputs["report"], outputs["n_sources"]).items():
        results.append({"key": key, "score": val})
    results.append({"key": "verified", "score": int(outputs["verified"])})
    return results


# --- runners -------------------------------------------------------------------
def ensure_dataset(client, topics):
    if not client.has_dataset(dataset_name=DATASET_NAME):
        ds = client.create_dataset(DATASET_NAME, description="Fixed research topics for comparing report quality between versions")
        client.create_examples(dataset_id=ds.id, examples=[{"inputs": {"topic": t}} for t in TOPICS])
        print(f"Created LangSmith dataset '{DATASET_NAME}' with {len(TOPICS)} topics")
    return [{"topic": t} for t in topics]


def run_langsmith(n_topics: int):
    from langsmith import Client, evaluate
    from evaluation.judge import langsmith_enabled

    if not langsmith_enabled():
        sys.exit("LangSmith is not configured. Set LANGSMITH_TRACING=true and LANGSMITH_API_KEY in .env, "
                 "or run with --local.")
    client = Client()
    ensure_dataset(client, TOPICS[:n_topics])
    examples = list(client.list_examples(dataset_name=DATASET_NAME))[:n_topics]
    results = evaluate(
        run_system,
        data=examples,
        evaluators=[score_report],
        experiment_prefix="pipeline",
        description="Real pipeline + LLM judge + citation checks",
        max_concurrency=1,          # one at a time: Groq free tier rate limits
        client=client,
    )
    print("\nDone. Open LangSmith → Datasets & Experiments → "
          f"'{DATASET_NAME}' to see the experiment '{results.experiment_name}'.")
    return results


def run_local(n_topics: int):
    rows = []
    for topic in TOPICS[:n_topics]:
        print(f"\n▶ {topic}")
        out = run_system({"topic": topic})
        scores = {r["key"]: r.get("value", r["score"]) for r in score_report({"topic": topic}, out)}
        rows.append((topic, scores, out))
    print("\n" + f"{'topic':<45} {'rel':>4} {'acc':>4} {'cla':>4} {'all':>5} {'cite%':>6} {'verif':>6}")
    for topic, s, _ in rows:
        print(f"{topic[:44]:<45} {s.get('relevance','-'):>4} {s.get('accuracy','-'):>4} "
              f"{s.get('clarity','-'):>4} {s.get('overall','-'):>5} "
              f"{int(s.get('citation_validity', 0) * 100):>5}% {s.get('verified', 0):>6}")
    return rows


def main(argv=None):
    p = argparse.ArgumentParser(description="Evaluate the real pipeline with the LLM judge")
    p.add_argument("--topics", type=int, default=len(TOPICS), help="how many topics to run (default all 5)")
    p.add_argument("--local", action="store_true", help="don't use LangSmith, just print results")
    args = p.parse_args(argv)
    n = max(1, min(args.topics, len(TOPICS)))
    return run_local(n) if args.local else run_langsmith(n)


if __name__ == "__main__":
    main()
