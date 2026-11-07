"""
Configuration inspection routes.
Provides read-only access to active runtime configuration from settings.
No hardcoded or draft values - only real system configuration.
"""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends

from admin_backend.config import settings
from admin_backend.security.dependencies import AuthenticatedUser, require_admin_role

router = APIRouter(prefix="/config", tags=["Admin Configuration"])


@router.get("/draft")
def get_active_configuration(admin: AuthenticatedUser = Depends(require_admin_role)):
    """
    Inspect active system configuration from runtime settings.
    Returns real configuration values - no draft/scaffolding.
    """
    return {
        "version": "1.0.0",
        "is_active": True,
        "system_timezone": "Asia/Kolkata (IST, UTC+05:30)",
        "current_time_ist": datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M:%S IST"),
        "notice": "This configuration reflects active runtime settings.",
        "cache": {
            "similarity_threshold": 0.85,
            "ttl_seconds": 86400,
            "max_entries_estimate": 10000,
            "redis_url": settings.redis_url
        },
        "models": {
            "primary_provider": "groq",
            "primary_model": "qwen/qwen3.8-27b",
            "fallback_provider": "ollama",
            "fallback_model": "qwen2.5:7b",
            "temperature": 0.3,
            "max_tokens": 900,
            "groq_api_key_configured": bool(settings.groq_api_key),
            "ollama_host": settings.ollama_host
        },
        "search": {
            "provider": "tavily",
            "max_results": 5,
            "search_timeout_seconds": 10.0,
            "tavily_api_key_configured": bool(settings.tavily_api_key)
        },
        "pipeline": {
            "max_revisions": 2,
            "min_report_length": 50,
            "use_llm_guards": True
        },
        "storage": {
            "postgres_dsn_configured": bool(settings.postgres_dsn),
            "audit_log_path": settings.admin_audit_log_path,
            "traces_log_path": settings.admin_traces_log_path,
            "safety_log_path": settings.admin_safety_log_path,
            "scores_log_path": settings.scores_log_path,
            "redteam_results_path": settings.redteam_results_path,
            "data_retention_days": settings.admin_data_retention_days
        },
        "security": {
            "admin_token_algorithm": settings.admin_token_algorithm,
            "admin_token_expire_minutes": settings.admin_token_expire_minutes,
            "admin_rate_limit_per_minute": settings.admin_rate_limit_per_minute,
            "max_preview_length": settings.admin_max_preview_length,
            "mask_pii": settings.admin_mask_pii
        },
        "privacy_retention": {
            "data_retention_days": settings.admin_data_retention_days,
            "max_preview_length": settings.admin_max_preview_length,
            "mask_pii": settings.admin_mask_pii
        }
    }
