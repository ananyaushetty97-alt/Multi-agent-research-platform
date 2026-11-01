"""
Unit tests for quality scores, LLM-as-a-judge logs, and human reviews.
"""
import json
import os
import tempfile
from admin_backend.models.quality import QualityFilter
from admin_backend.services.quality_service import QualityService


def test_quality_service_log_parsing_and_heuristics():
    # Create a temporary scores.jsonl
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".jsonl") as f:
        f.write(json.dumps({
            "time": "2026-10-25 00:18:30",
            "topic": "Impact of LLMs on healthcare",
            "relevance": 10,
            "accuracy": 9,
            "clarity": 8,
            "overall": 9.0,
            "comment": "The report is complete and well-structured, but cuts off abruptly in the final section.",
        }) + "\n")
        f.write(json.dumps({
            "time": "2026-10-26 10:00:00",
            "topic": "Solid-state batteries",
            "relevance": 10,
            "accuracy": 9,
            "clarity": 10,
            "overall": 9.7,
            "comment": "Thorough report with verifiable claims and accurate citations.",
        }) + "\n")
        f.write(json.dumps({
            "time": "2026-10-26 12:00:00",
            "topic": "Failed topic test",
            "error": "grading failed: timeout",
        }) + "\n")
        temp_path = f.name

    try:
        svc = QualityService(log_path=temp_path)
        records = svc.load_judge_records()

        assert len(records) == 3

        # First record has suspected truncation
        assert records[0].suspected_truncated is True
        assert "cuts off" in (records[0].truncation_reason or "").lower()

        # Second record is complete
        assert records[1].suspected_truncated is False
        assert records[1].overall == 9.7

        # Third record is a failed grading
        assert records[2].is_failed_grading is True
        assert "timeout" in (records[2].error_message or "")

        # Summary check
        summary = svc.get_quality_summary()
        assert summary.total_records == 3
        assert summary.successful_grades == 2
        assert summary.failed_grades == 1
        assert summary.suspected_truncated_count == 1

        # Filtering check
        failed_only = svc.query_scores(QualityFilter(only_failed=True))
        assert len(failed_only) == 1
        assert failed_only[0].is_failed_grading is True

        truncated_only = svc.query_scores(QualityFilter(only_suspected_truncated=True))
        assert len(truncated_only) == 1
        assert truncated_only[0].suspected_truncated is True

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_human_reviews_isolation():
    svc = QualityService()
    review = svc.add_human_review(
        topic="Microgrid electrification",
        reviewer_username="reviewer_jane",
        relevance=9,
        accuracy=8,
        clarity=9,
        feedback_notes="Solid technical depth; citations verified.",
    )

    assert review.reviewer_username == "reviewer_jane"
    assert review.overall == 8.7
    reviews = svc.list_human_reviews()
    assert len(reviews) == 1
    assert reviews[0].review_id == review.review_id
