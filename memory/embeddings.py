"""
Shared embedding helper.

Uses a local sentence-transformers model so this module has ZERO dependency
on the LLM gateway (Person C's call_llm()) or any external API key.
The model downloads once (a few hundred MB) the first time you run this,
then is cached locally by the library.
"""

from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from memory.config import settings


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    """Load the embedding model once and reuse it (loading is slow)."""
    return SentenceTransformer(settings.embedding_model_name)


def embed(text: str) -> list[float]:
    """
    Turn a piece of text into a fixed-length vector of floats.
    Same input text always produces the same vector.
    """
    if not text or not text.strip():
        raise ValueError("Cannot embed empty text")
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Returns a score from -1 to 1. Closer to 1 means more similar.
    Since embed() already returns normalized vectors, this is just a dot product,
    but we compute it the explicit way so this function works even with
    vectors from elsewhere that aren't pre-normalized.
    """
    a = np.array(vec_a)
    b = np.array(vec_b)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


if __name__ == "__main__":
    # Quick manual sanity check — run: python -m memory.embeddings
    pairs = [
        ("best budget laptops 2026", "cheap laptops worth buying in 2026"),
        ("best budget laptops 2026", "best budget phones 2026"),
        ("how does photosynthesis work", "explain the process of photosynthesis"),
        ("how does photosynthesis work", "latest news on the stock market"),
    ]
    print("Sanity check: similar pairs should score high, unrelated pairs low.\n")
    for a, b in pairs:
        score = cosine_similarity(embed(a), embed(b))
        print(f"{score:.3f}  |  '{a}'  vs  '{b}'")
