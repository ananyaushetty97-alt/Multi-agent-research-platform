from gateway.llm_gateway import call_llm
from graph.state import ResearchState
from agents.history_utils import last_report_entry


def router_agent(state: ResearchState) -> dict:
    history = state.get("conversation_history") or []

    # No report yet in this conversation: it can only be new research (no AI call needed)
    if not last_report_entry(history):
        return {"intent": "new_research"}

    recent = "\n".join(f"{h['role']}: {h['content'][:200]}" for h in history[-6:])
    prompt = f"""Conversation so far:
{recent}

New user message: "{state['topic']}"

Classify the new message as exactly one of:
- NEW_RESEARCH: a different topic, unrelated to the report above
- MODIFY: asks to change, shorten, expand or restructure the existing report
- QUESTION: asks something about the existing report without asking to change it

Reply with one word: NEW_RESEARCH, MODIFY or QUESTION."""

    result = call_llm(prompt, system_prompt="You are an intent classifier. Reply with exactly one word.")
    intent = result.strip().upper()
    if "MODIFY" in intent:
        return {"intent": "modify"}
    if "QUESTION" in intent:
        return {"intent": "question"}
    return {"intent": "new_research"}