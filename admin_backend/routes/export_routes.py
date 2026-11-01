"""
Data export routes for evaluation scores and quality history.
"""
from fastapi import APIRouter, Depends, Request, Response

from admin_backend.security.dependencies import AuthenticatedUser, require_admin_role
from admin_backend.services.export_service import export_service

router = APIRouter(prefix="/export", tags=["Admin Export"])


@router.get("/scores/csv")
def export_scores_csv(
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    Download evaluation score history as a CSV file.
    Audited in admin audit log.
    """
    client_ip = request.client.host if request.client else "unknown"
    csv_data = export_service.export_scores_to_csv(
        actor_username=admin.username,
        actor_role=admin.role,
        client_ip=client_ip,
    )
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=evaluation_scores.csv"},
    )


@router.get("/scores/json")
def export_scores_json(
    request: Request,
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    Download evaluation score history as formatted JSON.
    Audited in admin audit log.
    """
    client_ip = request.client.host if request.client else "unknown"
    json_data = export_service.export_scores_to_json(
        actor_username=admin.username,
        actor_role=admin.role,
        client_ip=client_ip,
    )
    return Response(
        content=json_data,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=evaluation_scores.json"},
    )
