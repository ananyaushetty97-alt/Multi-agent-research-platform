from gateway.llm_gateway import call_llm
from graph.state import ResearchState

def summarize_agent(state: ResearchState) -> dict:
    prompt = f"Summarize the key points from this research material:\n\n{state['search_results']}"
    summary = call_llm(prompt, system_prompt="You are an expert summarizer. Extract only the most important facts.")
    return {"summary": summary}