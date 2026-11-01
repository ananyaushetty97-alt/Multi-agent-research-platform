"""
Export service for evaluation scores, reports, and audit logs.
Generates CSV and JSON formats using standard Python libraries without modifying existing files.
"""
import csv
import io
import json
from typing import List

from admin_backend.models.audit import AuditAction
from admin_backend.models.quality import JudgeScoreRecord
from admin_backend.services.audit_service import audit_service
from admin_backend.services.quality_service import quality_service


class ExportService:
    def export_scores_to_csv(
        self,
        actor_username: str = "admin",
        actor_role: str = "admin",
        client_ip: str | None = None,
    ) -> str:
        """Export all evaluation scores as a CSV string."""
        records: List[JudgeScoreRecord] = quality_service.load_judge_records()

        output = io.StringIO()
        fieldnames = [
            "id", "timestamp", "topic", "relevance", "accuracy", "clarity",
            "overall", "comment", "is_failed_grading", "error_message",
            "suspected_truncated", "truncation_reason"
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for r in records:
            writer.writerow(r.model_dump())

        # Audit export action
        audit_service.log_action(
            actor_username=actor_username,
            actor_role=actor_role,
            action=AuditAction.EXPORT_DATA,
            resource_type="scores_csv",
            status="success",
            details={"rows_exported": len(records)},
            client_ip=client_ip,
        )

        return output.getvalue()

    def export_scores_to_json(
        self,
        actor_username: str = "admin",
        actor_role: str = "admin",
        client_ip: str | None = None,
    ) -> str:
        """Export all evaluation scores as formatted JSON."""
        records: List[JudgeScoreRecord] = quality_service.load_judge_records()
        data = [r.model_dump() for r in records]

        # Audit export action
        audit_service.log_action(
            actor_username=actor_username,
            actor_role=actor_role,
            action=AuditAction.EXPORT_DATA,
            resource_type="scores_json",
            status="success",
            details={"rows_exported": len(records)},
            client_ip=client_ip,
        )

        return json.dumps(data, indent=2)


export_service = ExportService()
