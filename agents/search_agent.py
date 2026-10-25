import os
from tavily import TavilyClient
from dotenv import load_dotenv
from graph.state import ResearchState

load_dotenv()
tavily = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))


def search_agent(state: ResearchState) -> dict:
    results = tavily.search(query=state["topic"], max_results=5)
    structured = [
        {
            "title": r.get("title") or r.get("url", "Untitled"),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
        }
        for r in results.get("results", [])
        if r.get("content")
    ]
    return {"search_results": structured}