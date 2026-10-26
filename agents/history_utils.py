def last_report_entry(history):
    """The most recent full report in the conversation (not Q&A answers)."""
    return next((h for h in reversed(history or []) if h.get("role") == "report"), None)