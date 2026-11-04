"""
Detailed platform health and dependency diagnostics routes.
Requires administrator privileges.
"""
from fastapi import APIRouter, Depends

from admin_backend.models.health import DetailedSystemHealth
from admin_backend.security.dependencies import AuthenticatedUser, require_admin_role
from admin_backend.services.health_service import health_service

router = APIRouter(prefix="/health", tags=["Admin Health"])


@router.get("", response_model=DetailedSystemHealth)
def get_detailed_system_health(
    admin: AuthenticatedUser = Depends(require_admin_role),
):
    """
    Perform synchronous reachability and latency checks across all external dependencies:
    API process, Redis, PostgreSQL with pgvector, Groq LLM API, local Ollama daemon, and Tavily search.
    Reports unavailable dependencies accurately without falsely labeling them healthy.
    """
    return health_service.get_full_health()
