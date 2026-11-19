from langgraph.graph import StateGraph, START, END
from graph.state import ResearchState
from agents.router_agent import router_agent
from agents.search_agent import search_agent
from agents.summarize_agent import summarize_agent
from agents.write_agent import write_agent
from agents.verify_agent import verify_agent
from agents.modify_agent import modify_agent
from agents.answer_agent import answer_agent
from guardrails.checks import guarded_search

MAX_REVISIONS = 2


def route_by_intent(state: ResearchState) -> str:
    intent = state.get("intent")
    if intent == "modify":
        return "modify"
    if intent == "question":
        return "answer"
    return "search"


def should_revise(state: ResearchState) -> str:
    if state["is_verified"] or state["revision_count"] >= MAX_REVISIONS:
        return "end"
    # A failed edit goes back to the editor, not to Write (Write would redo the whole report)
    return "revise_modify" if state.get("intent") == "modify" else "revise_write"


def build_pipeline():
    graph = StateGraph(ResearchState)
    graph.add_node("router", router_agent)
    graph.add_node("search", guarded_search(search_agent))  # removes hidden instructions from web pages
    graph.add_node("summarize", summarize_agent)
    graph.add_node("write", write_agent)
    graph.add_node("verify", verify_agent)
    graph.add_node("modify", modify_agent)
    graph.add_node("answer", answer_agent)

    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router", route_by_intent,
        {"search": "search", "modify": "modify", "answer": "answer"},
    )
    graph.add_edge("search", "summarize")
    graph.add_edge("summarize", "write")
    graph.add_edge("write", "verify")
    graph.add_edge("modify", "verify")
    graph.add_edge("answer", END)

    graph.add_conditional_edges(
        "verify", should_revise,
        {"revise_write": "write", "revise_modify": "modify", "end": END},
    )
    return graph.compile()


pipeline = build_pipeline()


def run_pipeline(topic: str, history: list | None = None, session_id: str | None = None) -> dict:
    return pipeline.invoke({
        "session_id": session_id,
        "topic": topic,
        "intent": None,
        "search_results": None,
        "summary": None,
        "report": None,
        "verification_notes": None,
        "is_verified": False,
        "revision_count": 0,
        "cache_hit": False,
        "conversation_history": history or [],
    })