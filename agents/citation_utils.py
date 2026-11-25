import re

SOURCES_HEADING = "## Sources"


def _get_cited_numbers(report: str) -> set[int]:
    """Extract all citation numbers from the report text."""
    cited_numbers = set()
    for match in re.finditer(r'\[(\d+(?:[,;\s]+\d+)*)\]', report):
        for num_str in re.split(r'[,;\s]+', match.group(1)):
            if num_str.isdigit():
                cited_numbers.add(int(num_str))
    return cited_numbers


def sources_block(search_results, report: str = "") -> str:
    """Builds the 'Sources' list from only the cited search results."""
    results = search_results or []
    if not results:
        return ""

    cited_numbers = _get_cited_numbers(report)

    # If no citations found, include all sources as fallback
    if not cited_numbers:
        lines = [
            f"- [{i + 1}] {r.get('title') or r.get('url')} — {r.get('url')}"
            for i, r in enumerate(results)
        ]
    else:
        # Only include sources that were actually cited
        lines = [
            f"- [{i + 1}] {r.get('title') or r.get('url')} — {r.get('url')}"
            for i, r in enumerate(results)
            if (i + 1) in cited_numbers
        ]

    return f"\n\n{SOURCES_HEADING}\n" + "\n".join(lines)


def strip_sources(report: str) -> str:
    """Removes the Sources section so the AI only sees/edits the body."""
    if not report:
        return ""
    idx = report.rfind(SOURCES_HEADING)
    return report[:idx].rstrip() if idx != -1 else report


def with_sources(body: str, search_results) -> str:
    """Body + Sources list. Safe to call twice (it strips any old list first).
    Only includes sources that are actually cited in the body."""
    return strip_sources(body) + sources_block(search_results, body)