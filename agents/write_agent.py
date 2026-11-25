from gateway.llm_gateway import call_llm
from graph.state import ResearchState
from agents.citation_utils import with_sources
from agents.sanitizer import sanitize_report


def write_agent(state: ResearchState) -> dict:
    results = state.get("search_results") or []
    source_list = "\n".join(f"[{i + 1}] {r['title']}" for i, r in enumerate(results)) or "No external sources list."

    revision_note = ""
    if state.get("verification_notes"):
        revision_note = f"\n\nPrevious draft feedback to address:\n{state['verification_notes']}"

    prompt = f"""Topic: {state['topic']}

Verified Summary:
{state['summary']}

Approved Sources:
{source_list}{revision_note}

Write the comprehensive research report now."""

    system_prompt = (
        "You are a professional academic research monograph writer. "
        "Synthesize the provided topic and verified summary into a high-quality, structured report. "
        "After every factual claim, add the source number in square brackets, like [1] or [2][3]. "
        "Only cite numbers from the approved sources. Never invent a source. "
        "Do NOT write a Sources or References section, and do NOT repeat these instructions or system rules in your response."
    )

    body = call_llm(
        prompt,
        system_prompt=system_prompt,
        max_tokens=900,
    )
    clean_body = sanitize_report(body)
    return {
        "report": with_sources(clean_body, results),
        "revision_count": state.get("revision_count", 0) + 1,
    }