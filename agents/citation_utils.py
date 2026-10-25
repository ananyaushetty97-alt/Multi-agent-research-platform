SOURCES_HEADING = "## Sources"


def sources_block(search_results) -> str:
    """Builds the 'Sources' list from the real search results (never from the AI)."""
    results = search_results or []
    if not results:
        return ""
    lines = [
        f"- [{i + 1}] {r.get('title') or r.get('url')} — {r.get('url')}"
        for i, r in enumerate(results)
    ]
    return f"\n\n{SOURCES_HEADING}\n" + "\n".join(lines)


def strip_sources(report: str) -> str:
    """Removes the Sources section so the AI only sees/edits the body."""
    if not report:
        return ""
    idx = report.rfind(SOURCES_HEADING)
    return report[:idx].rstrip() if idx != -1 else report


def with_sources(body: str, search_results) -> str:
    """Body + Sources list. Safe to call twice (it strips any old list first)."""
    return strip_sources(body) + sources_block(search_results)