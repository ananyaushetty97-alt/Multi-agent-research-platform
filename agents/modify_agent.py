from gateway.llm_gateway import call_llm
from graph.state import ResearchState
from agents.history_utils import last_report_entry
from agents.citation_utils import with_sources, strip_sources


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
        notes = f"\n\nA fact-check of your previous edit found these problems, fix them:\n{state['verification_notes']}"

    prompt = f"""Here is the existing report:

{base}

The user now asks: "{state['topic']}"

Revise the report to follow this request. Keep the [N] citation markers on every claim you keep,
and never invent a new source number. Do NOT add a Sources section. Return the full updated report.{notes}"""

    body = call_llm(prompt, system_prompt="You are a careful research report editor.")
    return {
        "report": with_sources(body, results),
        "search_results": results,
        "is_verified": False,
        "revision_count": state.get("revision_count", 0) + 1,
    }