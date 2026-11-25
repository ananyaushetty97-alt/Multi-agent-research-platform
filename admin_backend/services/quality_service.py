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


def _is_valid_uuid(val: str) -> bool:
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _is_valid_score(val) -> bool:
    return val is not None and isinstance(val, int) and (1 <= val <= 10)


def _mask_reviewer_identity(email: Optional[str], username: Optional[str]) -> str:
    identifier = (email or "").strip() or (username or "").strip()
    if not identifier:
        return "Anonymous"
    if "@" in identifier:
        parts = identifier.split("@", 1)
        local_part, domain = parts[0], parts[1]
        if len(local_part) <= 2:
            masked_local = local_part[0] + "***" if len(local_part) >= 1 else "***"
        else:
            masked_local = local_part[:2] + "***"
        return f"{masked_local}@{domain}"
    else:
        return identifier[:2] + "***" if len(identifier) > 2 else identifier[0] + "***"


class QualityService:
    def __init__(
        self,
        log_path: Optional[str] = None,
        human_reviews_path: Optional[str] = None,
        postgres_dsn: Optional[str] = None,
    ):
        self.log_path = log_path or settings.scores_log_path
        self.human_reviews_path = human_reviews_path or settings.admin_human_reviews_log_path
        self._human_reviews: List[HumanReviewScore] = []
        self.postgres_dsn: Optional[str] = postgres_dsn
        self._cached_human_reviews_count: Optional[int] = None
        self._count_cache_expires_at: float = 0.0
        self._count_cache_ttl_seconds: float = 30.0
        self._load_human_reviews()

    def _load_human_reviews(self) -> None:
        """Load human reviews from JSONL file."""
        if not os.path.exists(self.human_reviews_path):
            return
        try:
            with open(self.human_reviews_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        review = HumanReviewScore.model_validate(data)
                        self._human_reviews.append(review)
                    except Exception:
                        continue
            log.info(f"Loaded {len(self._human_reviews)} human reviews from {self.human_reviews_path}")
        except Exception as e:
            log.warning(f"Could not load human reviews from {self.human_reviews_path}: {e}")

    def _append_human_review(self, review: HumanReviewScore) -> None:
        """Append a human review to the JSONL file."""
        try:
            os.makedirs(os.path.dirname(self.human_reviews_path) or ".", exist_ok=True)
            with open(self.human_reviews_path, "a", encoding="utf-8") as f:
                f.write(review.model_dump_json() + "\n")
        except Exception as e:
            log.warning(f"Could not write human review to {self.human_reviews_path}: {e}")

    def get_postgres_dsn(self) -> Optional[str]:
        if self.postgres_dsn is not None:
            return self.postgres_dsn
        return settings.resolve_postgres_dsn()

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

    def count_human_reviews(self) -> int:
        """
        Count total unique human reviews across PostgreSQL user reviews and in-memory expert reviews.
        Validates scores (1-10) and handles non-UUID expert identifiers safely.
        Caches count with a TTL (default 30s) to minimize DB load.
        """
        import time
        now = time.monotonic()
        if self._cached_human_reviews_count is not None and now < self._count_cache_expires_at:
            return self._cached_human_reviews_count

        dsn = self.get_postgres_dsn()
        if not dsn or not dsn.strip():
            if self._cached_human_reviews_count is not None:
                return self._cached_human_reviews_count
            # No database configured: count the reviews saved in the file and in memory instead
            return len(self._reviews_without_database())

        try:
            import psycopg
            # Valid in-memory expert reviews filtering with strict [1, 10] checks
            valid_expert = [
                r for r in self._human_reviews
                if _is_valid_score(r.relevance) and _is_valid_score(r.accuracy) and _is_valid_score(r.clarity)
            ]

            # Unique expert review IDs
            unique_expert_ids = list({r.review_id for r in valid_expert})
            valid_uuid_expert_ids = [uid for uid in unique_expert_ids if _is_valid_uuid(uid)]

            with psycopg.connect(dsn, connect_timeout=2) as conn:
                with conn.cursor() as cur:
                    # 1. Count valid PostgreSQL user reviews
                    cur.execute("""
                        SELECT COUNT(*) FROM public.report_reviews
                        WHERE relevance IS NOT NULL AND relevance BETWEEN 1 AND 10
                          AND accuracy IS NOT NULL AND accuracy BETWEEN 1 AND 10
                          AND clarity IS NOT NULL AND clarity BETWEEN 1 AND 10;
                    """)
                    db_valid_count = cur.fetchone()[0] or 0

                    # 2. Overlap count by stable review UUID (safe against non-UUIDs)
                    uuid_overlap_count = 0
                    if valid_uuid_expert_ids:
                        cur.execute("""
                            SELECT COUNT(*) FROM public.report_reviews
                            WHERE id = ANY(%s::uuid[])
                              AND relevance IS NOT NULL AND relevance BETWEEN 1 AND 10
                              AND accuracy IS NOT NULL AND accuracy BETWEEN 1 AND 10
                              AND clarity IS NOT NULL AND clarity BETWEEN 1 AND 10;
                        """, (valid_uuid_expert_ids,))
                        uuid_overlap_count = cur.fetchone()[0] or 0

            # If in-memory review storage is active in test mode, include any valid in-memory reviews
            mem_valid_count = 0
            try:
                from user_auth.chat_storage import get_chat_review_storage, InMemoryChatReviewStorage
                c_storage = get_chat_review_storage()
                if isinstance(c_storage, InMemoryChatReviewStorage):
                    mem_revs = c_storage.list_all_reviews()
                    mem_valid_count = sum(
                        1 for r in mem_revs
                        if _is_valid_score(r.get("relevance")) and _is_valid_score(r.get("accuracy")) and _is_valid_score(r.get("clarity"))
                    )
            except Exception:
                pass

            deduped_total = (db_valid_count if db_valid_count > 0 else mem_valid_count) + (len(unique_expert_ids) - uuid_overlap_count)
            self._cached_human_reviews_count = deduped_total
            self._count_cache_expires_at = time.monotonic() + self._count_cache_ttl_seconds
            return deduped_total
        except Exception as e:
            if self._cached_human_reviews_count is not None:
                return self._cached_human_reviews_count
            log.warning(f"PostgreSQL unavailable for review count, using saved reviews instead: {e}")
            return len(self._reviews_without_database())

    def get_quality_summary(self) -> QualitySummary:
        """Compute aggregated metrics across all judge scores and human reviews."""
        records = self.load_judge_records()
        total = len(records)
        human_count = self.count_human_reviews()
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
                human_reviews_count=human_count,
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
            human_reviews_count=human_count,
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
        is_expert: bool = True,
    ) -> HumanReviewScore:
        """Record human review score separate from automated judge scores."""
        from datetime import datetime, timezone
        overall = round((relevance + accuracy + clarity) / 3.0, 1) if (
            _is_valid_score(relevance) and _is_valid_score(accuracy) and _is_valid_score(clarity)
        ) else 0.0
        review = HumanReviewScore(
            review_id=str(uuid.uuid4()),
            report_id=report_id,
            topic=topic,
            reviewer_username=reviewer_username,
            review_timestamp=datetime.now(timezone.utc).isoformat(),
            relevance=relevance if _is_valid_score(relevance) else 1,
            accuracy=accuracy if _is_valid_score(accuracy) else 1,
            clarity=clarity if _is_valid_score(clarity) else 1,
            overall=overall if overall > 0 else 1.0,
            feedback_notes=feedback_notes,
            flagged_for_rerun=flagged_for_rerun,
            reviewed=True,
            is_expert=is_expert,
        )
        self._human_reviews.append(review)
        self._append_human_review(review)
        self.invalidate_human_reviews_count_cache()
        return review

    def invalidate_human_reviews_count_cache(self) -> None:
        """Invalidate the cached count of human reviews so subsequent counts re-query immediately."""
        self._cached_human_reviews_count = None
        self._count_cache_expires_at = 0.0

    def list_human_reviews(self) -> List[HumanReviewScore]:
        """
        List all human reviews: retrieves genuine user reviews from PostgreSQL public.report_reviews,
        applies strict score validation (1-10), formats username with (user) and email masking,
        merges in-memory admin/expert reviews with (expert), and deduplicates strictly by review_id.
        """
        db_reviews: List[HumanReviewScore] = []
        dsn = self.get_postgres_dsn()
        if not dsn or not dsn.strip():
            # No database configured: show the reviews saved in the file and in memory
            return self._reviews_without_database()
        try:
            import psycopg
            from psycopg.rows import dict_row
            query = """
                SELECT r.id, r.report_id, r.user_id, r.topic, r.relevance, r.accuracy, r.clarity,
                       r.comment, r.created_at,
                       COALESCE(u.username, u.name, app_u.username) AS username,
                       COALESCE(u.email, app_u.email) AS email
                FROM public.report_reviews r
                LEFT JOIN public.users u ON r.user_id = u.id
                LEFT JOIN public.app_users app_u ON r.user_id = app_u.id
                ORDER BY r.created_at DESC
            """
            with psycopg.connect(dsn, connect_timeout=2, row_factory=dict_row) as conn:
                with conn.cursor() as cur:
                    cur.execute(query)
                    rows = cur.fetchall()
                    for row in rows:
                        rel = row.get("relevance")
                        acc = row.get("accuracy")
                        cla = row.get("clarity")
                        if not _is_valid_score(rel) or not _is_valid_score(acc) or not _is_valid_score(cla):
                            log.warning(f"[DATA INTEGRITY ALERT] Skipping malformed database review {row.get('id')}: invalid score values.")
                            continue

                        overall = round((rel + acc + cla) / 3.0, 1)
                        masked_ident = _mask_reviewer_identity(row.get("email"), row.get("username"))
                        reviewer_display = f"{masked_ident} (user)"

                        created_at = row.get("created_at")
                        review_ts = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at or "")

                        item = HumanReviewScore(
                            review_id=str(row["id"]),
                            report_id=str(row.get("report_id") or ""),
                            topic=str(row.get("topic") or "Research Monograph"),
                            reviewer_username=reviewer_display,
                            review_timestamp=review_ts,
                            relevance=rel,
                            accuracy=acc,
                            clarity=cla,
                            overall=overall,
                            feedback_notes=row.get("comment"),
                            flagged_for_rerun=False,
                            is_expert=False,
                        )
                        db_reviews.append(item)
        except Exception as e:
            log.warning(f"PostgreSQL unavailable for human reviews, using saved reviews instead: {e}")
            return self._reviews_without_database()

        # In-memory storage integration (for offline / unit-test modes using InMemoryChatReviewStorage)
        try:
            from user_auth.chat_storage import get_chat_review_storage, InMemoryChatReviewStorage
            c_storage = get_chat_review_storage()
            if isinstance(c_storage, InMemoryChatReviewStorage):
                mem_revs = c_storage.list_all_reviews()
                for mr in mem_revs:
                    rel = mr.get("relevance")
                    acc = mr.get("accuracy")
                    cla = mr.get("clarity")
                    if not _is_valid_score(rel) or not _is_valid_score(acc) or not _is_valid_score(cla):
                        continue
                    overall = round((rel + acc + cla) / 3.0, 1)
                    masked_ident = _mask_reviewer_identity(mr.get("reviewer_email"), mr.get("reviewer_username"))
                    reviewer_display = f"{masked_ident} (user)"
                    db_reviews.append(HumanReviewScore(
                        review_id=str(mr["id"]),
                        report_id=str(mr.get("report_id") or ""),
                        topic=str(mr.get("topic") or "Research Monograph"),
                        reviewer_username=reviewer_display,
                        review_timestamp=str(mr.get("created_at") or ""),
                        relevance=rel,
                        accuracy=acc,
                        clarity=cla,
                        overall=overall,
                        feedback_notes=mr.get("comment"),
                        flagged_for_rerun=False,
                        is_expert=False,
                    ))
        except Exception as e:
            log.debug(f"In-memory chat storage inspection skipped: {e}")

        seen_ids = set()
        merged: List[HumanReviewScore] = []
        for r in db_reviews:
            if r.review_id not in seen_ids:
                seen_ids.add(r.review_id)
                merged.append(r)

        # In-memory holds expert reviews only
        for expert_rev in reversed(self._human_reviews):
            # Score validation
            if not _is_valid_score(expert_rev.relevance) or not _is_valid_score(expert_rev.accuracy) or not _is_valid_score(expert_rev.clarity):
                log.warning(f"[DATA INTEGRITY ALERT] Skipping malformed in-memory expert review {expert_rev.review_id}: invalid score values.")
                continue

            # Deduplicate strictly by stable review ID
            if expert_rev.review_id in seen_ids:
                continue

            seen_ids.add(expert_rev.review_id)
            merged.append(self._labelled(expert_rev))

        return merged

    @staticmethod
    def _labelled(review: HumanReviewScore) -> HumanReviewScore:
        """Add '(expert)' or '(user)' to the reviewer name, based on the review's own flag."""
        if review.is_expert:
            suffix = " (expert)"
        else:
            suffix = " (user)"
        name = review.reviewer_username
        if name.endswith(" (expert)") or name.endswith(" (user)"):
            return review
        return review.model_copy(update={"reviewer_username": f"{name}{suffix}"})

    def _memory_chat_reviews(self) -> List[HumanReviewScore]:
        """User reviews held by the in-memory chat/review storage (offline and test mode)."""
        found: List[HumanReviewScore] = []
        try:
            from user_auth.chat_storage import get_chat_review_storage, InMemoryChatReviewStorage
            c_storage = get_chat_review_storage()
            if not isinstance(c_storage, InMemoryChatReviewStorage):
                return found
            for mr in c_storage.list_all_reviews():
                rel = mr.get("relevance")
                acc = mr.get("accuracy")
                cla = mr.get("clarity")
                if not _is_valid_score(rel) or not _is_valid_score(acc) or not _is_valid_score(cla):
                    continue
                masked_ident = _mask_reviewer_identity(mr.get("reviewer_email"), mr.get("reviewer_username"))
                found.append(HumanReviewScore(
                    review_id=str(mr["id"]),
                    report_id=str(mr.get("report_id") or ""),
                    topic=str(mr.get("topic") or "Research Monograph"),
                    reviewer_username=f"{masked_ident} (user)",
                    review_timestamp=str(mr.get("created_at") or ""),
                    relevance=rel,
                    accuracy=acc,
                    clarity=cla,
                    overall=round((rel + acc + cla) / 3.0, 1),
                    feedback_notes=mr.get("comment"),
                    flagged_for_rerun=False,
                    is_expert=False,
                ))
        except Exception as e:
            log.debug(f"In-memory chat storage inspection skipped: {e}")
        return found

    def _reviews_without_database(self) -> List[HumanReviewScore]:
        """All reviews available when PostgreSQL is not: in-memory user reviews + file-saved reviews."""
        merged: List[HumanReviewScore] = []
        seen_ids = set()
        for r in self._memory_chat_reviews():
            if r.review_id not in seen_ids:
                seen_ids.add(r.review_id)
                merged.append(r)
        for r in reversed(self._human_reviews):
            if not _is_valid_score(r.relevance) or not _is_valid_score(r.accuracy) or not _is_valid_score(r.clarity):
                continue
            if r.review_id in seen_ids:
                continue
            seen_ids.add(r.review_id)
            merged.append(self._labelled(r))
        return merged


# No seeding - only real data from actual judge scores and human reviews
quality_service = QualityService()

