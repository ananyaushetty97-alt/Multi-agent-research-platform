"""
Integration layer: where the other modules plug in.
If a real function can't be found, a stub (a harmless fake) is used instead.
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
HISTORY_PATHS = [("memory", "get_history")]
APPEND_PATHS = [("memory", "append_turn")]


# ---- Stubs (fake versions) -------------------------------------------------
def stub_run_pipeline(topic: str, history=None, session_id=None) -> str:
    from llm_link import call_llm
    return call_llm(
        f"Write a short, well-structured research report (about 300 words) on: {topic}. "
        "Use headings: Overview, Key Points, Conclusion."
    )


def stub_check_cache(topic: str):
    return None


def stub_save_to_ltm(report, topic=None, score=None, search_results=None):
    return None


_stub_sessions = {}


def stub_get_history(session_id):
    return list(_stub_sessions.get(session_id, []))


def stub_append_turn(session_id, entry):
    _stub_sessions.setdefault(session_id, []).append(entry)


# ---- Loader ----------------------------------------------------------------
def _load(paths, stub, name):
    for module_name, fn_name in paths:
        try:
            fn = getattr(importlib.import_module(module_name), fn_name)
            log.info(f"{name}: using REAL {module_name}.{fn_name}")
            return fn, False
        except (ImportError, AttributeError) as e:
            log.info(f"{name}: {module_name}.{fn_name} skipped ({type(e).__name__}: {e})")
            continue
    log.info(f"{name}: using STUB")
    return stub, True


run_pipeline, PIPELINE_IS_STUB = _load(PIPELINE_PATHS, stub_run_pipeline, "run_pipeline")
check_cache, CACHE_IS_STUB = _load(CACHE_PATHS, stub_check_cache, "check_cache")
save_to_ltm, LTM_IS_STUB = _load(LTM_PATHS, stub_save_to_ltm, "save_to_ltm")
get_history, HISTORY_IS_STUB = _load(HISTORY_PATHS, stub_get_history, "get_history")
append_turn, APPEND_IS_STUB = _load(APPEND_PATHS, stub_append_turn, "append_turn")


def report_to_text(report) -> str:
    """The pipeline may return a str, a dict, or an object. Turn any of them into text."""
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