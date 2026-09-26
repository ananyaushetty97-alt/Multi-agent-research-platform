import os
from tavily import TavilyClient
from dotenv import load_dotenv
from graph.state import ResearchState

load_dotenv()
tavily = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))

def search_agent(state: ResearchState) -> dict:
    topic = state["topic"]
    results = tavily.search(query=topic, max_results=5)
    combined = "\n\n".join([r["content"] for r in results["results"]])
    return {"search_results": combined}