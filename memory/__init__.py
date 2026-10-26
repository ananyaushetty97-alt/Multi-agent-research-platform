from memory.semantic_cache import SemanticCache
from memory.ltm import LongTermMemory
from memory.embeddings import embed
from memory.stm import SessionStore

_cache = SemanticCache()
_ltm = LongTermMemory()
_ltm.init_schema()
_sessions = SessionStore()

MAX_HISTORY_ENTRIES = 12


def check_cache(topic: str):
    result = _cache.lookup(topic)
    return result["report"] if result else None   # a dict: report, score, search_results


def save_to_ltm(report: str, topic: str | None = None, score: dict | None = None,
                search_results: list | None = None):
    sources = [{"title": r.get("title"), "url": r.get("url")} for r in (search_results or [])]
    _ltm.store_report(
        text=report,
        embedding=embed(report),
        metadata={"topic": topic, "sources": sources} if topic else {},
    )
    if topic:
        _cache.store(topic, {"report": report, "score": score, "search_results": search_results})


def get_history(session_id: str) -> list:
    data = _sessions.get(session_id) or {}
    history = list(data.get("history", []))
    last = data.get("last_report")
    # The newest report is kept separately, so long Q&A chats can't push it out
    if last and not any(h.get("role") == "report" for h in history):
        history.insert(0, last)
    return history


def append_turn(session_id: str, entry: dict) -> None:
    data = _sessions.get(session_id) or {}
    history = data.get("history", [])
    history.append(entry)
    data["history"] = history[-MAX_HISTORY_ENTRIES:]
    if entry.get("role") == "report":
        data["last_report"] = entry
    _sessions.set(session_id, data)