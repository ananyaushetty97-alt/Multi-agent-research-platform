import os
from urllib.parse import urlparse
from tavily import TavilyClient
from dotenv import load_dotenv
from graph.state import ResearchState

load_dotenv()
tavily = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))

DEFAULT_MAX_RESULTS = int(os.environ.get("MAX_SEARCH_RESULTS", "7"))

# Domains to strictly exclude from research reports (social media, user-generated posts, unverified forums)
EXCLUDED_DOMAINS = [
    "linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com",
    "tiktok.com", "pinterest.com", "reddit.com", "quora.com", "medium.com",
    "tumblr.com", "threads.net"
]

# Tier 1: Highest authority scientific, peer-reviewed, academic, and government repositories
TIER1_AUTHORITY_DOMAINS = {
    "arxiv.org", "nature.com", "ieee.org", "sciencedirect.com", "springer.com",
    "nih.gov", "ncbi.nlm.nih.gov", "pubmed.ncbi.nlm.nih.gov", "acm.org", "cell.com",
    "wiley.com", "jstor.org", "biorxiv.org", "medrxiv.org", "science.org",
    "thelancet.com", "who.int", "cdc.gov", "nasa.gov", "pnas.org"
}

# Tier 2: Reputable tech/news, institutional, and research-grade knowledge bases
TIER2_AUTHORITY_DOMAINS = {
    "reuters.com", "bloomberg.com", "bbc.com", "mit.edu", "stanford.edu",
    "techcrunch.com", "wired.com", "theverge.com", "arstechnica.com",
    "wikipedia.org", "github.com"
}


def _calculate_authority_score(url: str, base_score: float = 0.5) -> float:
    """Score domain credibility to prioritize verified academic and official sources."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
    except Exception:
        return base_score

    # Check for top academic / gov TLDs
    if domain.endswith((".edu", ".gov", ".ac.uk", ".edu.in", ".gov.in")):
        return base_score + 0.40

    # Check for Tier 1 scientific repositories
    if any(domain == d or domain.endswith("." + d) for d in TIER1_AUTHORITY_DOMAINS):
        return base_score + 0.35

    # Check for non-profit organizations (.org)
    if domain.endswith(".org"):
        return base_score + 0.20

    # Check for Tier 2 reputable outlets
    if any(domain == d or domain.endswith("." + d) for d in TIER2_AUTHORITY_DOMAINS):
        return base_score + 0.15

    return base_score


def search_agent(state: ResearchState) -> dict:
    max_needed = DEFAULT_MAX_RESULTS
    # Fetch slightly more candidates so we can filter and pick the highest-authority ones
    query_candidates = min(max_needed + 4, 15)

    try:
        results = tavily.search(
            query=state["topic"],
            max_results=query_candidates,
            search_depth="advanced",
            exclude_domains=EXCLUDED_DOMAINS
        )
        raw_items = results.get("results", [])

        structured = []
        for r in raw_items:
            content = r.get("content", "").strip()
            url = r.get("url", "").strip()
            if not content or not url:
                continue

            # Fallback filter in case search engine allowed an excluded domain
            domain_lower = urlparse(url).netloc.lower()
            if any(ex in domain_lower for ex in EXCLUDED_DOMAINS):
                continue

            tavily_score = float(r.get("score") or 0.5)
            authority_score = _calculate_authority_score(url, tavily_score)
            structured.append({
                "title": r.get("title") or r.get("url", "Untitled"),
                "url": url,
                "content": content,
                "score": authority_score,
            })

        # Sort by authority/credibility descending so the best verified sources come first
        structured.sort(key=lambda x: x["score"], reverse=True)
        top_sources = structured[:max_needed]

        # Strip internal score before returning clean search results
        cleaned_sources = [
            {"title": s["title"], "url": s["url"], "content": s["content"]}
            for s in top_sources
        ]
        return {"search_results": cleaned_sources}

    except Exception as e:
        import logging
        logging.getLogger("search_agent").warning(f"Tavily search failed ({e}), proceeding with empty results")
        return {"search_results": []}
