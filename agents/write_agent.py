from gateway.llm_gateway import call_llm
from graph.state import ResearchState

def write_agent(state: ResearchState) -> dict:
    revision_note = ""
    if state.get("verification_notes"):
        revision_note = f"\n\nPrevious draft had these issues, fix them:\n{state['verification_notes']}"

    prompt = f"Write a well-structured research report on '{state['topic']}' using this summary:\n\n{state['summary']}{revision_note}"
    report = call_llm(prompt, system_prompt="You are a professional research report writer.")
    return {
        "report": report,
        "revision_count": state.get("revision_count", 0) + 1
    }