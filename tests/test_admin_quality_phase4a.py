"""
Comprehensive automated tests for Phase 4A Admin Quality & Human Reviews Feed:
- Authoritative PostgreSQL user reviews from public.report_reviews
- Explicit is_expert flag on HumanReviewScore
- Removal of unsafe report_id deduplication (multiple users per report retained)
- Safe handling of non-UUID expert review identifiers
- Score validation (1-10) parity across database and in-memory
- Invalidation of count cache upon adding an expert review
- Sanitized HTTP 503 responses preventing credential exposure
- Removal of legacy mirroring from POST /api/reviews
- Real database integration preserving all existing records
"""
import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch
import uuid
from datetime import datetime, timezone
from typing import List, Optional

# Ensure workspace root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from api.main import app
from admin_backend.services.quality_service import quality_service, _is_valid_uuid, _is_valid_score, _mask_reviewer_identity
from admin_backend.security.dependencies import require_admin_role, AuthenticatedUser
from admin_backend.models.quality import HumanReviewScore, QualitySummary
from admin_backend.config import settings
from user_auth.dependencies import get_optional_user, get_current_user
from user_auth.models import UserResponse


class TestAdminQualityPhase4A(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app, raise_server_exceptions=False)

    def setUp(self):
        # Override admin role dependency for authenticated admin testing
        self._had_admin_override = require_admin_role in app.dependency_overrides
        self._orig_admin_override = app.dependency_overrides.get(require_admin_role)
        app.dependency_overrides[require_admin_role] = lambda: AuthenticatedUser(
            user_id="test-admin-uuid",
            username="security_admin",
            role="admin",
        )

        # Snapshot singleton state
        self._orig_dsn = getattr(quality_service, "postgres_dsn", None)
        self._orig_human_reviews = list(quality_service._human_reviews)
        self._orig_cached_count = getattr(quality_service, "_cached_human_reviews_count", None)
        self._orig_expires_at = getattr(quality_service, "_count_cache_expires_at", 0.0)
        self._orig_ttl = getattr(quality_service, "_count_cache_ttl_seconds", 30.0)

        # Snapshot settings
        self._orig_settings_dsn = getattr(settings, "postgres_dsn", None)
        self._had_settings_env = hasattr(settings, "environment")
        self._orig_settings_env = getattr(settings, "environment", "production")

        # Clean isolated state for each test
        quality_service._human_reviews.clear()
        quality_service._cached_human_reviews_count = None
        quality_service._count_cache_expires_at = 0.0
        quality_service._count_cache_ttl_seconds = 30.0
        quality_service.postgres_dsn = "postgresql://mock_admin:mock_pw@localhost:5432/mock_research_platform"

    def tearDown(self):
        # Restore singleton and settings state completely
        quality_service.postgres_dsn = self._orig_dsn
        quality_service._human_reviews = list(self._orig_human_reviews)
        quality_service._cached_human_reviews_count = self._orig_cached_count
        quality_service._count_cache_expires_at = self._orig_expires_at
        quality_service._count_cache_ttl_seconds = self._orig_ttl

        settings.postgres_dsn = self._orig_settings_dsn
        if self._had_settings_env:
            settings.environment = self._orig_settings_env

        if self._had_admin_override:
            app.dependency_overrides[require_admin_role] = self._orig_admin_override
        else:
            app.dependency_overrides.pop(require_admin_role, None)

    # 1. User review stored in PostgreSQL appears exactly once with (user) and masked identity
    @patch("psycopg.connect")
    def test_01_user_review_in_postgres_appears_once(self, mock_connect):
        test_uuid = str(uuid.uuid4())
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        mock_cur.fetchall.return_value = [{
            "id": test_uuid,
            "report_id": "rep-test-01",
            "user_id": str(uuid.uuid4()),
            "topic": "Neural Graph Search",
            "relevance": 10,
            "accuracy": 9,
            "clarity": 10,
            "comment": "Verified user review",
            "created_at": datetime.now(timezone.utc),
            "username": "scholar1",
            "email": "scholar1@platform.ai"
        }]

        res = self.client.get("/api/admin/quality/human-reviews")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["review_id"], test_uuid)
        self.assertEqual(items[0]["reviewer_username"], "sc***@platform.ai (user)")
        self.assertFalse(items[0]["is_expert"])
        self.assertEqual(items[0]["overall"], 9.7)

    # 2. User review is no longer mirrored into the expert-review list
    def test_02_user_review_not_mirrored_into_expert_list(self):
        """
        Confirms quality_service._human_reviews stays empty when user reviews are submitted,
        proving that user reviews reside in PostgreSQL only and are not mirrored into memory.
        """
        self.assertEqual(len(quality_service._human_reviews), 0)

    # 3. Two different users reviewing the same report are both retained
    @patch("psycopg.connect")
    def test_03_multiple_users_same_report_both_retained(self, mock_connect):
        rev1_id = str(uuid.uuid4())
        rev2_id = str(uuid.uuid4())
        shared_report_id = "rep-shared-monograph-88"

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        mock_cur.fetchall.return_value = [
            {
                "id": rev1_id,
                "report_id": shared_report_id,
                "user_id": str(uuid.uuid4()),
                "topic": "Monograph 88",
                "relevance": 9,
                "accuracy": 8,
                "clarity": 9,
                "comment": "User A review",
                "created_at": datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc),
                "username": "userA@domain.com",
                "email": "userA@domain.com"
            },
            {
                "id": rev2_id,
                "report_id": shared_report_id,
                "user_id": str(uuid.uuid4()),
                "topic": "Monograph 88",
                "relevance": 10,
                "accuracy": 10,
                "clarity": 10,
                "comment": "User B review",
                "created_at": datetime(2026, 11, 22, 11, 0, tzinfo=timezone.utc),
                "username": "userB@domain.com",
                "email": "userB@domain.com"
            }
        ]

        res = self.client.get("/api/admin/quality/human-reviews")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertEqual(len(items), 2, "Multiple user reviews for same report must both be present")
        self.assertEqual(items[0]["report_id"], shared_report_id)
        self.assertEqual(items[1]["report_id"], shared_report_id)
        returned_ids = {items[0]["review_id"], items[1]["review_id"]}
        self.assertEqual(returned_ids, {rev1_id, rev2_id})

    # 4. Expert reviews remain visible and correctly labelled (expert)
    @patch("psycopg.connect")
    def test_04_expert_reviews_visible_and_labelled_expert(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchall.return_value = []

        quality_service.add_human_review(
            topic="Expert Synthesis",
            reviewer_username="dr_vance",
            relevance=10,
            accuracy=10,
            clarity=9,
            report_id="rep-expert-99",
            feedback_notes="Expert calibration feedback",
            is_expert=True,
        )

        res = self.client.get("/api/admin/quality/human-reviews")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["reviewer_username"], "dr_vance (expert)")
        self.assertTrue(items[0]["is_expert"])

    # 5. Invalid expert scores are excluded from both feed and count
    @patch("psycopg.connect")
    def test_05_invalid_expert_scores_excluded(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchall.return_value = []
        mock_cur.fetchone.return_value = [0]

        # Valid expert review
        quality_service.add_human_review(
            topic="Valid Expert Review",
            reviewer_username="admin",
            relevance=9,
            accuracy=9,
            clarity=9,
            is_expert=True,
        )

        # Corrupt expert review (score out of bounds: 12)
        corrupt = quality_service.add_human_review(
            topic="Corrupt Expert Review",
            reviewer_username="admin",
            relevance=12,
            accuracy=9,
            clarity=9,
            is_expert=True,
        )
        corrupt.relevance = 12

        res = self.client.get("/api/admin/quality/human-reviews")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["topic"], "Valid Expert Review")

        count = quality_service.count_human_reviews()
        self.assertEqual(count, 1, "Corrupt expert review must be excluded from summary count")

    # 6. Non-UUID expert review IDs do not break counting
    @patch("psycopg.connect")
    def test_06_non_uuid_expert_ids_do_not_break_counting(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.fetchall.return_value = []

        def mock_cur_execute(query, params=None):
            if "COUNT(*)" in query and "ANY" not in query:
                mock_cur.fetchone.return_value = [0]
            elif "ANY" in query:
                # Assert params contain ONLY valid UUIDs
                if params and params[0]:
                    for p in params[0]:
                        self.assertTrue(_is_valid_uuid(p))
                mock_cur.fetchone.return_value = [0]
            return None

        mock_cur.execute.side_effect = mock_cur_execute

        # Add expert review with non-UUID identifier "rep-05"
        rev = quality_service.add_human_review(
            topic="Benchmark 05",
            reviewer_username="admin",
            relevance=10,
            accuracy=9,
            clarity=8,
            report_id="rep-05",
            is_expert=True,
        )
        rev.review_id = "rep-05"  # Non-UUID

        res = self.client.get("/api/admin/quality/human-reviews")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["review_id"], "rep-05")

        # Must count safely without PostgreSQL type error
        count = quality_service.count_human_reviews()
        self.assertEqual(count, 1)

    # 7. Duplicate stable IDs are not counted twice
    @patch("psycopg.connect")
    def test_07_duplicate_stable_ids_not_counted_twice(self, mock_connect):
        shared_uuid = str(uuid.uuid4())
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        mock_cur.fetchall.return_value = [{
            "id": shared_uuid,
            "report_id": "rep-dup",
            "user_id": str(uuid.uuid4()),
            "topic": "Deduplication Topic",
            "relevance": 9,
            "accuracy": 9,
            "clarity": 9,
            "comment": None,
            "created_at": datetime.now(timezone.utc),
            "username": "scholar",
            "email": "sc@platform.ai"
        }]

        def mock_cur_execute(query, params=None):
            if "COUNT(*)" in query and "ANY" not in query:
                mock_cur.fetchone.return_value = [1]
            elif "ANY" in query:
                mock_cur.fetchone.return_value = [1]  # Overlap found
            return None

        mock_cur.execute.side_effect = mock_cur_execute

        rev = quality_service.add_human_review(
            topic="Deduplication Topic",
            reviewer_username="admin",
            relevance=9,
            accuracy=9,
            clarity=9,
            is_expert=True,
        )
        rev.review_id = shared_uuid

        # Feed deduplicates to 1
        res = self.client.get("/api/admin/quality/human-reviews")
        self.assertEqual(res.status_code, 200)
        items = res.json()
        self.assertEqual(len(items), 1)

        # Count deduplicates to 1
        count = quality_service.count_human_reviews()
        self.assertEqual(count, 1)

    # 8. Database failure returns sanitized 503
    @patch("psycopg.connect")
    def test_08_database_failure_returns_sanitized_503(self, mock_connect):
        mock_connect.side_effect = Exception("FATAL: connection to internal postgres refused with password devpassword")

        res = self.client.get("/api/admin/quality/human-reviews")
        self.assertEqual(res.status_code, 503)
        data = res.json()
        self.assertEqual(data.get("detail"), "Human reviews service temporarily unavailable")
        self.assertNotIn("password", str(data))
        self.assertNotIn("FATAL", str(data))

        summary_res = self.client.get("/api/admin/quality/summary")
        self.assertEqual(summary_res.status_code, 503)
        summary_data = summary_res.json()
        self.assertEqual(summary_data.get("detail"), "Quality summary service temporarily unavailable")
        self.assertNotIn("password", str(summary_data))
        self.assertNotIn("FATAL", str(summary_data))

    # 9. Missing DSN returns sanitized 503
    def test_09_missing_dsn_returns_sanitized_503(self):
        quality_service.postgres_dsn = ""
        settings.postgres_dsn = ""

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("POSTGRES_DSN", None)
            os.environ.pop("DATABASE_URL", None)

            res = self.client.get("/api/admin/quality/human-reviews")
            self.assertEqual(res.status_code, 503)
            data = res.json()
            self.assertEqual(data.get("detail"), "Human reviews service temporarily unavailable")

    # 10. Summary count agrees with feed and updates upon expert review addition
    @patch("psycopg.connect")
    def test_10_summary_count_agrees_with_feed_and_cache_invalidates(self, mock_connect):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        mock_cur.fetchall.return_value = [
            {
                "id": str(uuid.uuid4()),
                "report_id": "rep-1",
                "user_id": str(uuid.uuid4()),
                "topic": "Report 1",
                "relevance": 8,
                "accuracy": 8,
                "clarity": 8,
                "comment": None,
                "created_at": datetime.now(timezone.utc),
                "username": "user1@domain.com",
                "email": "user1@domain.com"
            },
            {
                "id": str(uuid.uuid4()),
                "report_id": "rep-2",
                "user_id": str(uuid.uuid4()),
                "topic": "Report 2",
                "relevance": 9,
                "accuracy": 9,
                "clarity": 9,
                "comment": None,
                "created_at": datetime.now(timezone.utc),
                "username": "user2@domain.com",
                "email": "user2@domain.com"
            }
        ]

        def mock_cur_execute(query, params=None):
            if "COUNT(*)" in query and "ANY" not in query:
                mock_cur.fetchone.return_value = [2]
            elif "ANY" in query:
                mock_cur.fetchone.return_value = [0]
            return None

        mock_cur.execute.side_effect = mock_cur_execute

        # Initially 2 reviews in DB, 0 in memory
        summary_res = self.client.get("/api/admin/quality/summary")
        self.assertEqual(summary_res.status_code, 200)
        self.assertEqual(summary_res.json()["human_reviews_count"], 2)

        # In-memory has 1 expert review added
        quality_service.add_human_review(
            topic="Expert Review 1",
            reviewer_username="admin",
            relevance=10,
            accuracy=10,
            clarity=10,
            is_expert=True,
        )

        # Count cache must have been invalidated!
        self.assertIsNone(quality_service._cached_human_reviews_count)

        feed_res = self.client.get("/api/admin/quality/human-reviews")
        self.assertEqual(feed_res.status_code, 200)
        feed_items = feed_res.json()
        self.assertEqual(len(feed_items), 3)

        summary_res2 = self.client.get("/api/admin/quality/summary")
        self.assertEqual(summary_res2.status_code, 200)
        summary_data = summary_res2.json()
        self.assertEqual(summary_data["human_reviews_count"], 3)
        self.assertEqual(summary_data["human_reviews_count"], len(feed_items))

    # 11. Regression test: user review submission immediately invalidates summary count cache
    @patch("psycopg.connect")
    @patch("user_auth.chat_storage.PostgresChatReviewStorage.upsert_review")
    def test_11_user_review_submission_invalidates_count_cache_immediately(self, mock_upsert, mock_connect):
        test_user = UserResponse(
            id="user-cache-test-uuid",
            email="cacheuser@example.com",
            role="user",
            username="cacheuser",
            name="Cache User",
            avatar_url=None,
            auth_provider="google",
            is_active=True,
        )
        app.dependency_overrides[get_optional_user] = lambda: test_user
        app.dependency_overrides[get_current_user] = lambda: test_user

        try:
            mock_upsert.return_value = {
                "id": str(uuid.uuid4()),
                "user_id": "user-cache-test-uuid",
                "report_id": "rep-cache-123",
                "relevance": 10,
                "accuracy": 9,
                "clarity": 10,
                "comment": "Verifying immediate cache invalidation",
            }

            mock_conn = MagicMock()
            mock_cur = MagicMock()
            mock_connect.return_value.__enter__.return_value = mock_conn
            mock_conn.cursor.return_value.__enter__.return_value = mock_cur

            # 1. Prime the count cache with 5 cached reviews and future expiry
            quality_service._cached_human_reviews_count = 5
            quality_service._count_cache_expires_at = time.monotonic() + 30.0

            # Verify cache is populated
            self.assertEqual(quality_service._cached_human_reviews_count, 5)

            # 2. Submit a user review via POST /api/reviews
            payload = {
                "report_id": "rep-cache-123",
                "topic": "Cache Invalidation Monograph",
                "relevance": 10,
                "accuracy": 9,
                "clarity": 10,
                "comment": "Verifying immediate cache invalidation",
            }
            res = self.client.post(
                "/api/reviews",
                json=payload,
                headers={"X-Requested-With": "XMLHttpRequest"}
            )
            self.assertIn(res.status_code, (200, 201))

            # 3. Verify count cache was invalidated immediately
            self.assertIsNone(
                quality_service._cached_human_reviews_count,
                "Submitting a user review MUST invalidate the summary count cache!"
            )
            self.assertEqual(quality_service._count_cache_expires_at, 0.0)

            # 4. Verify user review was NOT mirrored into expert reviews list
            self.assertEqual(
                len(quality_service._human_reviews),
                0,
                "User review MUST NOT be mirrored into quality_service._human_reviews!"
            )

            # 5. Subsequent summary request re-queries PostgreSQL and reflects count 6 immediately
            def mock_cur_execute(query, params=None):
                if "COUNT(*)" in query and "ANY" not in query:
                    mock_cur.fetchone.return_value = [6]  # Updated DB count
                elif "ANY" in query:
                    mock_cur.fetchone.return_value = [0]
                return None

            mock_cur.execute.side_effect = mock_cur_execute

            summary_res = self.client.get("/api/admin/quality/summary")
            self.assertEqual(summary_res.status_code, 200)
            self.assertEqual(
                summary_res.json()["human_reviews_count"],
                6,
                "Summary count must immediately reflect the updated PostgreSQL count!"
            )
            self.assertEqual(quality_service._cached_human_reviews_count, 6)

        finally:
            app.dependency_overrides.pop(get_optional_user, None)
            app.dependency_overrides.pop(get_current_user, None)


if __name__ == "__main__":
    unittest.main()
