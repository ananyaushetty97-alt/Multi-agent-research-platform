from memory.semantic_cache import SemanticCache
from memory.ltm import LongTermMemory
from memory.embeddings import embed

_cache = SemanticCache()
_ltm = LongTermMemory()
_ltm.init_schema()


def check_cache(topic: str):
    result = _cache.lookup(topic)
    if not result:
        return None
    return result["report"]  # this is now the {"report": ..., "score": ...} dict we stored


def save_to_ltm(report: str, topic: str | None = None, score: dict | None = None):
    _ltm.store_report(
        text=report,
        embedding=embed(report),
        metadata={"topic": topic} if topic else {}
    )
    if topic:
        _cache.store(topic, {"report": report, "score": score})