from graph.pipeline import pipeline

def run_pipeline(topic: str):
    initial_state = {
        "topic": topic,
        "search_results": None,
        "summary": None,
        "report": None,
        "verification_notes": None,
        "is_verified": False,
        "revision_count": 0
    }
    return pipeline.invoke(initial_state)

if __name__ == "__main__":
    result = run_pipeline("The impact of renewable energy on grid stability")
    print("=== FINAL REPORT ===")
    print(result["report"])
    print("\n=== VERIFIED ===", result["is_verified"])
    print("=== REVISIONS ===", result["revision_count"])