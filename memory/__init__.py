from memory.semantic_cache import SemanticCache
from memory.ltm import LongTermMemory
from memory.embeddings import embed

_cache = SemanticCache()
_ltm = LongTermMemory()
_ltm.init_schema()


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