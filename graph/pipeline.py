from langgraph.graph import StateGraph, START, END
from graph.state import ResearchState
from agents.search_agent import search_agent
from agents.summarize_agent import summarize_agent
from agents.write_agent import write_agent
from agents.verify_agent import verify_agent
from guardrails.checks import guarded_search

MAX_REVISIONS = 2


def should_revise(state: ResearchState) -> str:
    if state["is_verified"] or state["revision_count"] >= MAX_REVISIONS:
        return "end"
    return "revise"


def build_pipeline():
    graph = StateGraph(ResearchState)
    graph.add_node("search", guarded_search(search_agent))  # strips injected instructions from web pages
    graph.add_node("summarize", summarize_agent)
    graph.add_node("write", write_agent)
    graph.add_node("verify", verify_agent)

    graph.add_edge(START, "search")
    graph.add_edge("search", "summarize")
    graph.add_edge("summarize", "write")
    graph.add_edge("write", "verify")
    graph.add_conditional_edges("verify", should_revise, {"revise": "write", "end": END})
    return graph.compile()


pipeline = build_pipeline()


def run_pipeline(topic: str) -> dict:
    """Returns the whole final state (report, search_results, is_verified, ...)."""
    return pipeline.invoke({
        "topic": topic,
        "search_results": None,
        "summary": None,
        "report": None,
        "verification_notes": None,
        "is_verified": False,
        "revision_count": 0,
        "cache_hit": False,
    })