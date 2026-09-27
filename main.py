from graph.pipeline import pipeline
from memory.semantic_cache import SemanticCache
from memory.ltm import LongTermMemory  # confirm this filename matches Person 2's actual file
from memory.embeddings import embed

cache = SemanticCache()
ltm = LongTermMemory()

# Run once at startup — idempotent, safe to call every time
ltm.init_schema()


def run_pipeline(topic: str):
    # 1. Check semantic cache first
    cache_result = cache.lookup(topic)

    if cache_result:
        return {
            "topic": topic,
            "search_results": None,
            "summary": None,
            "report": cache_result["report"],
            "verification_notes": None,
            "is_verified": True,
            "revision_count": 0,
            "cache_hit": True
        }

    # 2. Cache miss — run the full 4-agent pipeline
    initial_state = {
        "topic": topic,
        "search_results": None,
        "summary": None,
        "report": None,
        "verification_notes": None,
        "is_verified": False,
        "revision_count": 0,
        "cache_hit": False
    }
    final_state = pipeline.invoke(initial_state)

    # 3. If verified, save to both the semantic cache and long-term memory
    if final_state["is_verified"]:
        cache.store(topic, final_state["report"])
        ltm.store_report(
            text=final_state["report"],
            embedding=embed(final_state["report"]),
            metadata={"topic": topic}
        )

    return final_state


if __name__ == "__main__":
    topic = "The impact of renewable energy on grid stability"

    print("=== FIRST CALL (expect cache MISS) ===")
    result1 = run_pipeline(topic)
    print("Cache hit:", result1["cache_hit"])
    print("Report:", result1["report"][:300], "...\n")

    print("=== SECOND CALL, same topic (expect cache HIT) ===")
    result2 = run_pipeline(topic)
    print("Cache hit:", result2["cache_hit"])
    print("Report:", result2["report"][:300], "...")