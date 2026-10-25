from gateway.llm_gateway import call_llm
from graph.state import ResearchState
from agents.citation_utils import strip_sources


def verify_agent(state: ResearchState) -> dict:
    results = state.get("search_results") or []
    source_text = "\n\n".join(
        f"[{i + 1}] {r['title']}\n{r['content'][:1500]}" for i, r in enumerate(results)
    )
    body = strip_sources(state["report"])

    prompt = f"""You are checking a research report against its source material.

SOURCE MATERIAL (numbered):
{source_text}

REPORT (cites sources as [N]):
{body}

Check only these two things:
1. Every [N] in the report is a number that exists in the source material above.
2. Specific facts (numbers, dates, names, statistics) are supported by the source they cite.

Do not fail the report for general statements that have no citation.
Reply with exactly the word VERIFIED if both checks pass.
Otherwise list each problem on its own line."""

    result = call_llm(prompt, system_prompt="You are a strict but fair fact-checker.")
    cleaned = result.lstrip("*#`\"' \n").upper()
    is_verified = cleaned.startswith("VERIFIED")
    return {
        "is_verified": is_verified,
        "verification_notes": None if is_verified else result,
    }