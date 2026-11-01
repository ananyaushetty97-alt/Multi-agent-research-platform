import logging
from memory.semantic_cache import SemanticCache
from memory.ltm import LongTermMemory
from memory.embeddings import embed
from memory.stm import SessionStore

log = logging.getLogger("memory")

_cache = SemanticCache()
_ltm = LongTermMemory()
_sessions = SessionStore()
_memory_sessions: dict = {}
_schema_initialized = False


def _ensure_schema():
    global _schema_initialized
    if not _schema_initialized:
        try:
            _ltm.init_schema()
            _schema_initialized = True
        except Exception as e:
            log.warning(f"LTM schema initialization skipped (offline/unreachable: {e})")


MAX_HISTORY_ENTRIES = 12


def check_cache(topic: str):
    try:
        result = _cache.lookup(topic)
        return result["report"] if result else None   # a dict: report, score, search_results
    except Exception as e:
        log.warning(f"check_cache failed ({e})")
        return None


def save_to_ltm(report: str, topic: str | None = None, score: dict | None = None,
                search_results: list | None = None):
    _ensure_schema()
    sources = [{"title": r.get("title"), "url": r.get("url")} for r in (search_results or [])]
    try:
        _ltm.store_report(
            text=report,
            embedding=embed(report),
            metadata={"topic": topic, "sources": sources} if topic else {},
        )
    except Exception as e:
        log.warning(f"save_to_ltm database store failed ({e})")

    if topic:
        try:
            _cache.store(topic, {"report": report, "score": score, "search_results": search_results})
        except Exception as e:
            log.warning(f"save_to_ltm cache store failed ({e})")


def get_history(session_id: str) -> list:
    data = None
    try:
        data = _sessions.get(session_id)
    except Exception as e:
        log.warning(f"get_history redis get failed, using in-memory store: {e}")
        data = _memory_sessions.get(session_id)

    if not data and session_id in _memory_sessions:
        data = _memory_sessions[session_id]

    data = data or {}
    history = list(data.get("history", []))
    last = data.get("last_report")
    # The newest report is kept separately, so long Q&A chats can't push it out
    if last and not any(h.get("role") == "report" for h in history):
        history.insert(0, last)
    return history


def append_turn(session_id: str, entry: dict) -> None:
    data = None
    try:
        data = _sessions.get(session_id)
    except Exception as e:
        log.warning(f"append_turn redis get failed, using in-memory store: {e}")
        data = _memory_sessions.get(session_id)

    if not data and session_id in _memory_sessions:
        data = _memory_sessions[session_id]

    data = data or {}
    history = data.get("history", [])
    history.append(entry)
    data["history"] = history[-MAX_HISTORY_ENTRIES:]
    if entry.get("role") == "report":
        data["last_report"] = entry

    _memory_sessions[session_id] = data

    try:
        _sessions.set(session_id, data)
    except Exception as e:
        log.warning(f"append_turn redis set failed: {e}")