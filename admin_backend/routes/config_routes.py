"""
Configuration inspection routes.
Provides read-only access to draft schemas and proposed system limits
WITHOUT mutating active runtime configuration.
"""
from fastapi import APIRouter, Depends

from admin_backend.models.config_schemas import SystemConfigDraft
from admin_backend.security.dependencies import AuthenticatedUser, require_admin_role

router = APIRouter(prefix="/config", tags=["Admin Configuration"])


@router.get("/draft", response_model=SystemConfigDraft)
def get_draft_configuration(admin: AuthenticatedUser = Depends(require_admin_role)):
    """
    Inspect proposed system limits and draft schemas for cache similarity threshold,
    model routing (Groq vs Ollama), search limits, and retry thresholds.
    Notice: These settings are draft blueprints and do NOT mutate active runtime behavior.
    """
    return SystemConfigDraft()
