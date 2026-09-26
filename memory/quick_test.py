"""
Run this after setup to confirm the whole memory module works end to end.

    python -m memory.quick_test

If every section prints without errors and the results look sensible,
your module is fully working: Redis, Postgres+pgvector, and the embedding
model are all reachable and correct.
"""

from memory.embeddings import cosine_similarity, embed
from memory.ltm import LongTermMemory
from memory.semantic_cache import SemanticCache
from memory.stm import SessionStore


def check_embeddings():
    print("\n[1/4] Embeddings")
    a = embed("best budget laptops for students")
    b = embed("cheap laptops worth buying for college students")
    c = embed("history of the Roman aqueduct system")
    print(f"  similar pair similarity:   {cosine_similarity(a, b):.3f}  (expect high, > 0.6)")
    print(f"  unrelated pair similarity: {cosine_similarity(a, c):.3f}  (expect low, < 0.4)")


def check_stm():
    print("\n[2/4] Short-term memory (Redis)")
    store = SessionStore(ttl_seconds=30)
    assert store.ping(), "Redis is not reachable — is docker compose up?"
    store.set("quicktest-session", {"topic": "demo", "step": "search"})
    print("  wrote and read back:", store.get("quicktest-session"))
    store.delete("quicktest-session")
    print("  after delete:", store.get("quicktest-session"))


def check_ltm():
    print("\n[3/4] Long-term memory (Postgres + pgvector)")
    ltm = LongTermMemory()
    ltm.init_schema()
    report_id = ltm.store_report(
        text="Demo report about budget laptops",
        embedding=embed("Demo report about budget laptops"),
        metadata={"quicktest": True},
    )
    results = ltm.find_similar(embed("affordable laptops for college"), top_k=1)
    print("  closest match:", results[0]["text"], f"(similarity={results[0]['similarity']:.3f})")
    ltm.delete_report(report_id)
    print("  cleaned up test row")


def check_semantic_cache():
    print("\n[4/4] Semantic cache")
    cache = SemanticCache(ttl_seconds=30)
    cache.clear_all()
    cache.store(topic="best budget laptops 2026", report={"summary": "demo report"})
    hit = cache.lookup("cheap laptops worth buying in 2026")
    miss = cache.lookup("history of the Roman aqueduct system")
    print("  near-duplicate lookup (expect a hit):", "HIT" if hit else "MISS")
    print("  unrelated lookup (expect a miss):    ", "HIT" if miss else "MISS")
    cache.clear_all()


if __name__ == "__main__":
    print("Running memory module sanity check...")
    check_embeddings()
    check_stm()
    check_ltm()
    check_semantic_cache()
    print("\nAll checks completed. If the numbers above look sensible, you're good to go.")
