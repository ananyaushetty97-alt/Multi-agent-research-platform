"""
Quality assessment service reading evaluation logs and separating automated LLM-as-a-judge scores from human reviews.
Only returns REAL data from actual judge scores and human reviews - no seeded/fake data.
"""
import json
import logging
import os
import uuid
from typing import Dict, List, Optional

from admin_backend.config import settings
from admin_backend.models.quality import (
    HumanReviewScore,
    JudgeScoreRecord,
    QualityFilter,
    QualitySummary,
)

log = logging.getLogger("admin_backend.quality")


class QualityService:
    def __init__(self, log_path: Optional[str] = None):
        self.log_path = log_path or settings.scores_log_path
        self._human_reviews: List[HumanReviewScore] = []

    def load_judge_records(self) -> List[JudgeScoreRecord]:
        """
        Safely parse judge scoring history from the JSONL log file.
        Gracefully returns an empty list if the log file does not exist.
        """
        if not os.path.exists(self.log_path):
            return []

        records: List[JudgeScoreRecord] = []
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                for idx, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    comment = data.get("comment", "")

                    record = JudgeScoreRecord(
                        id=str(data.get("id") or f"score-{idx+1}"),
                        timestamp=str(data.get("time", "")),
                        topic=str(data.get("topic", "")),
                        relevance=data.get("relevance"),
                        accuracy=data.get("accuracy"),
                        clarity=data.get("clarity"),
                        overall=float(data["overall"]) if data.get("overall") is not None else None,
                        comment=comment,
                    )
                    records.append(record)
        except Exception as e:
            log.warning(f"Error reading scores log at {self.log_path}: {e}")

        return records

    def query_scores(self, filter_opts: QualityFilter) -> List[JudgeScoreRecord]:
        """Query and filter judge scores."""
        records = self.load_judge_records()

        # Apply filters
        if filter_opts.min_overall is not None:
            records = [r for r in records if r.overall is not None and r.overall >= filter_opts.min_overall]
        if filter_opts.max_overall is not None:
            records = [r for r in records if r.overall is not None and r.overall <= filter_opts.max_overall]
        if filter_opts.search_topic:
            q = filter_opts.search_topic.lower()
            records = [r for r in records if q in r.topic.lower()]

        # Newest first
        records = list(reversed(records))
        start = filter_opts.offset
        end = start + filter_opts.limit
        return records[start:end]

    def get_quality_summary(self) -> QualitySummary:
        """Compute aggregated metrics across all judge scores and human reviews."""
        records = self.load_judge_records()
        total = len(records)
        if total == 0:
            return QualitySummary(
                total_records=0,
                successful_grades=0,
                failed_grades=0,
                average_overall=None,
                average_relevance=None,
                average_accuracy=None,
                average_clarity=None,
                low_scoring_count=0,
                human_reviews_count=len(self._human_reviews),
            )

        successful = [r for r in records if r.overall is not None]
        failed_count = total - len(successful)

        avg_overall = round(sum(r.overall for r in successful) / len(successful), 2) if successful else None
        avg_rel = (
            round(sum(r.relevance for r in successful if r.relevance is not None) / len(successful), 2)
            if successful else None
        )
        avg_acc = (
            round(sum(r.accuracy for r in successful if r.accuracy is not None) / len(successful), 2)
            if successful else None
        )
        avg_cla = (
            round(sum(r.clarity for r in successful if r.clarity is not None) / len(successful), 2)
            if successful else None
        )

        low_scores = sum(1 for r in successful if r.overall is not None and r.overall < 7.0)

        return QualitySummary(
            total_records=total,
            successful_grades=len(successful),
            failed_grades=failed_count,
            average_overall=avg_overall,
            average_relevance=avg_rel,
            average_accuracy=avg_acc,
            average_clarity=avg_cla,
            low_scoring_count=low_scores,
            human_reviews_count=len(self._human_reviews),
        )

    # Human review isolation
    def add_human_review(
        self,
        topic: str,
        reviewer_username: str,
        relevance: int,
        accuracy: int,
        clarity: int,
        report_id: Optional[str] = None,
        feedback_notes: Optional[str] = None,
        flagged_for_rerun: bool = False,
    ) -> HumanReviewScore:
        """Record human review score separate from automated judge scores."""
        from datetime import datetime, timezone
        overall = round((relevance + accuracy + clarity) / 3.0, 1)
        review = HumanReviewScore(
            review_id=str(uuid.uuid4()),
            report_id=report_id,
            topic=topic,
            reviewer_username=reviewer_username,
            review_timestamp=datetime.now(timezone.utc).isoformat(),
            relevance=relevance,
            accuracy=accuracy,
            clarity=clarity,
            overall=overall,
            feedback_notes=feedback_notes,
            flagged_for_rerun=flagged_for_rerun,
            reviewed=True,
        )
        self._human_reviews.append(review)
        return review

    def list_human_reviews(self) -> List[HumanReviewScore]:
        return list(reversed(self._human_reviews))


# No seeding - only real data from actual judge scores and human reviews
quality_service = QualityService()

