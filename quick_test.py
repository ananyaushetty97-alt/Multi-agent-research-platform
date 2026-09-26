from agents.search_agent import search_agent
from agents.summarize_agent import summarize_agent
from agents.write_agent import write_agent
from agents.verify_agent import verify_agent

# Shared starting state, same shape as your real ResearchState
state = {
    "topic": "quantum computing",
    "search_results": None,
    "summary": None,
    "report": None,
    "verification_notes": None,
    "is_verified": False,
    "revision_count": 0
}

print("=== Testing Search Agent ===")
result = search_agent(state)
state.update(result)
print(state["search_results"][:300], "...\n")   # print first 300 chars so it's readable

print("=== Testing Summarize Agent ===")
result = summarize_agent(state)
state.update(result)
print(state["summary"], "\n")

print("=== Testing Write Agent ===")
result = write_agent(state)
state.update(result)
print(state["report"][:300], "...\n")

print("=== Testing Verify Agent ===")
result = verify_agent(state)
state.update(result)
print("Verified:", state["is_verified"])
print("Notes:", state["verification_notes"])