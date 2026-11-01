from gateway.llm_gateway import call_llm
from graph.state import ResearchState
from agents.citation_utils import with_sources


def write_agent(state: ResearchState) -> dict:
    results = state.get("search_results") or []
    source_list = "\n".join(f"[{i + 1}] {r['title']}" for i, r in enumerate(results)) or "No external sources list."

    revision_note = ""
    if state.get("verification_notes"):
        revision_note = f"\n\nYour previous draft had these problems, fix them:\n{state['verification_notes']}"

    prompt = f"""Write a well-structured research report on '{state['topic']}' using this summary:

{state['summary']}

Sources you may cite:
{source_list}

Rules:
- After every factual claim, add the source number in square brackets, like [1] or [2][3].
- Only cite numbers from the list above. Never invent a source.
- Do NOT write a Sources or References section. It is added automatically.{revision_note}"""

    body = call_llm(
        prompt,
        system_prompt="You are a professional research report writer who cites every claim.",
    )
    return {
        "report": with_sources(body, results),
        "revision_count": state.get("revision_count", 0) + 1,
    }