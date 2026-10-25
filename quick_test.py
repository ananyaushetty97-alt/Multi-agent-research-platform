from graph.pipeline import run_pipeline

r = run_pipeline("Impact of renewable energy on grid stability")
print(r["report"])
print("\nverified:", r["is_verified"], "| revisions:", r["revision_count"])
print("sources:", [s["url"] for s in r["search_results"]])
print("has [1]:", "[1]" in r["report"], "| has Sources block:", "## Sources" in r["report"])