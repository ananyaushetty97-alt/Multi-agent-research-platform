from gateway.llm_gateway import call_llm
from graph.state import ResearchState


def summarize_agent(state: ResearchState) -> dict:
    results = state.get("search_results") or []
    sources_text = "\n\n".join(
        f"[Source {i + 1}] {r['title']} ({r['url']})\n{r['content'][:2000]}"
        for i, r in enumerate(results)
    )

    if not results:
        prompt = f"Summarize key verified facts about: {state['topic']}. Present each point clearly."
        summary = call_llm(
            prompt,
            system_prompt="You are an expert research analyst who provides factual, balanced overviews.",
        )
        return {"summary": summary}

    prompt = f"""Summarize the key facts from the sources below.
After every fact, note which source it came from using its number, like [1] or [2][3].
Only use information that appears in the sources.

{sources_text}"""

    summary = call_llm(
        prompt,
        system_prompt="You are an expert summarizer who always tracks which source each fact came from.",
    )
    return {"summary": summary}