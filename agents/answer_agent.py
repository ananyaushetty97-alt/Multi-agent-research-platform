from gateway.llm_gateway import call_llm
from graph.state import ResearchState
from agents.history_utils import last_report_entry
from agents.citation_utils import strip_sources


def answer_agent(state: ResearchState) -> dict:
    last = last_report_entry(state.get("conversation_history")) or {}
    report = strip_sources(last.get("content", ""))

    prompt = f"""Based only on this report:

{report}

Answer this question: "{state['topic']}"

If the report does not contain enough information, say so instead of guessing.
Keep the [N] citation markers on facts you use."""

    answer = call_llm(prompt, system_prompt="You answer strictly from the provided report.")
    return {
        "report": answer,
        "search_results": last.get("search_results"),
        "is_verified": True,
        "revision_count": 0,
    }