"""
Integration layer — where Person A's and Person B's code plugs in.

On Day 1 their code doesn't exist yet, so we use STUBS (fake versions) and the
API still runs end to end. On Day 2, once their branches are merged into main,
this file finds their real functions automatically.

If their function lives somewhere unexpected, add the path to the lists below.
Example: ("graph.pipeline", "run_pipeline") means `from graph.pipeline import run_pipeline`.
"""
import importlib
import logging

log = logging.getLogger("integration")

PIPELINE_PATHS = [("graph.pipeline", "run_pipeline"), ("graph", "run_pipeline"),
                  ("agents.pipeline", "run_pipeline"), ("agents", "run_pipeline")]
CACHE_PATHS = [("memory.cache", "check_cache"), ("memory.semantic_cache", "check_cache"),
               ("memory", "check_cache")]
LTM_PATHS = [("memory.ltm", "save_to_ltm"), ("memory.long_term", "save_to_ltm"),
             ("memory", "save_to_ltm")]


# ---- Stubs (fake versions for Day 1) ------------------------------------
def stub_run_pipeline(topic: str) -> str:
    """Pretends to be Person A's agents, but uses the team gateway so the demo is real."""
    from llm_link import call_llm
    return call_llm(
        f"Write a short, well-structured research report (about 300 words) on: {topic}. "
        "Use headings: Overview, Key Points, Conclusion."
    )


def stub_check_cache(topic: str):
    return None  # always a cache miss


def stub_save_to_ltm(report, topic: str | None = None):
    return None  # does nothing


# ---- Loader -------------------------------------------------------------
def _load(paths, stub, name):
    for module_name, fn_name in paths:
        try:
            fn = getattr(importlib.import_module(module_name), fn_name)
            log.info(f"{name}: using REAL {module_name}.{fn_name}")
            return fn, False
        except (ImportError, AttributeError):
            continue
    log.info(f"{name}: using STUB")
    return stub, True


run_pipeline, PIPELINE_IS_STUB = _load(PIPELINE_PATHS, stub_run_pipeline, "run_pipeline")
check_cache, CACHE_IS_STUB = _load(CACHE_PATHS, stub_check_cache, "check_cache")
save_to_ltm, LTM_IS_STUB = _load(LTM_PATHS, stub_save_to_ltm, "save_to_ltm")


def report_to_text(report) -> str:
    """Person A may return a str, a dict, or an object. Turn any of them into text."""
    if report is None:
        return ""
    if isinstance(report, str):
        return report
    if isinstance(report, dict):
        for key in ("report", "content", "text", "final_report", "draft"):
            if report.get(key):
                return str(report[key])
        return str(report)
    for attr in ("content", "text", "report"):
        if getattr(report, attr, None):
            return str(getattr(report, attr))
    return str(report)
