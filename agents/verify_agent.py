from gateway.llm_gateway import call_llm
from graph.state import ResearchState

def verify_agent(state: ResearchState) -> dict:
    prompt = f"""Check this report for unsupported claims or factual issues, comparing it against the original research:

Original research: {state['search_results']}

Report: {state['report']}

Reply with exactly "VERIFIED" if the report is accurate and well-supported.
Otherwise, list the specific issues found."""

    result = call_llm(prompt, system_prompt="You are a strict fact-checker.")
    is_verified = "VERIFIED" in result.upper()
    return {
        "is_verified": is_verified,
        "verification_notes": None if is_verified else result
    }