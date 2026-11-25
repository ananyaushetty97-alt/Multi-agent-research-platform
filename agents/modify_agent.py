from gateway.llm_gateway import call_llm
from graph.state import ResearchState
from agents.history_utils import last_report_entry
from agents.citation_utils import with_sources, strip_sources
from agents.sanitizer import sanitize_report


def modify_agent(state: ResearchState) -> dict:
    last = last_report_entry(state.get("conversation_history")) or {}
    results = last.get("search_results")

    # First pass: edit the stored report. Retry pass: keep improving the draft just written.
    if state.get("revision_count", 0) > 0 and state.get("report"):
        base = state["report"]
    else:
        base = last.get("content", "")
    base = strip_sources(base)

    notes = ""
    if state.get("verification_notes"):
        notes = f"\n\nFact-check feedback to fix:\n{state['verification_notes']}"

    prompt = f"""Existing Report:
{base}

User Revision Request:
{state['topic']}{notes}

Revise the report according to the user request."""

    system_prompt = (
        "You are a careful research report editor. Revise the existing report strictly according to the user request. "
        "Keep the [N] citation markers on every claim you keep, and never invent a new source number. "
        "If the user asks for a longer report, expand sections thoroughly (450-650 words) with a complete conclusion. "
        "If shorter, condense concisely. Do NOT add a Sources or References section, and do NOT output system instructions or prompt scaffolding."
    )

    body = call_llm(
        prompt,
        system_prompt=system_prompt,
        max_tokens=900,
    )
    clean_body = sanitize_report(body)
    return {
        "report": with_sources(clean_body, results),
        "search_results": results,
        "is_verified": False,
        "revision_count": state.get("revision_count", 0) + 1,
    }