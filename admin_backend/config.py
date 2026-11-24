"""
Configuration settings for the isolated admin backend.
Reads configuration from environment variables with safe defaults.
Does NOT store or expose hardcoded secrets or default credentials.
"""
import os
import secrets
import logging
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("admin_backend.config")


class AdminSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Security & Auth
    # Persistent ADMIN_JWT_SECRET or ADMIN_SECRET_KEY in production .env.
    admin_jwt_secret: Optional[str] = None
    admin_secret_key: str = ""
    admin_token_algorithm: str = "HS256"
    admin_token_expire_minutes: int = 60
    admin_rate_limit_per_minute: int = 120
    admin_cookie_name: str = "admin_session"
    admin_jwt_issuer: str = "research-platform-admin"
    admin_jwt_audience: str = "admin-portal"
    google_client_id: Optional[str] = None

    # Storage paths
    admin_audit_log_path: str = os.path.join("logs", "admin_audit.jsonl")
    admin_traces_log_path: str = os.path.join("logs", "admin_traces.jsonl")
    admin_safety_log_path: str = os.path.join("logs", "admin_safety.jsonl")
    scores_log_path: str = os.path.join("logs", "scores.jsonl")
    redteam_results_path: str = os.path.join("logs", "redteam_results.json")

    # Environment
    environment: str = "production"

    # Dependency Connection URLs (for health probes & future live adapters)
    redis_url: str = "redis://localhost:6379/0"
    postgres_dsn: Optional[str] = None
    dev_postgres_dsn_fallback: Optional[str] = None
    dev_postgres_fallback_allowed: bool = False
    groq_api_key: Optional[str] = None
    ollama_host: str = "http://localhost:11434"
    tavily_api_key: Optional[str] = None

    # Privacy & Retention
    admin_data_retention_days: int = 30
    admin_max_preview_length: int = 160
    admin_mask_pii: bool = True

    def resolve_postgres_dsn(self) -> Optional[str]:
        """
        Resolves the PostgreSQL DSN strictly honoring precedence:
        1. Explicitly configured postgres_dsn or POSTGRES_DSN / DATABASE_URL environment variables.
        2. Development fallback only if environment == 'development' and fallback is explicitly allowed.
        3. Returns None if unconfigured.
        """
        primary = self.postgres_dsn or os.environ.get("POSTGRES_DSN") or os.environ.get("DATABASE_URL")
        if primary and primary.strip():
            return primary.strip()
        if (
            getattr(self, "environment", "production").lower() == "development"
            and getattr(self, "dev_postgres_fallback_allowed", False)
            and getattr(self, "dev_postgres_dsn_fallback", None)
            and self.dev_postgres_dsn_fallback.strip()
        ):
            return self.dev_postgres_dsn_fallback.strip()
        return None

    def get_signing_key(self) -> bytes:
        """
        Returns the signing key as bytes.
        Checks ADMIN_JWT_SECRET, admin_jwt_secret, ADMIN_SECRET_KEY, admin_secret_key.
        Enforces minimum length of 32 characters in production.
        """
        key = (
            self.admin_jwt_secret
            or os.environ.get("ADMIN_JWT_SECRET")
            or self.admin_secret_key
            or os.environ.get("ADMIN_SECRET_KEY")
            or ""
        )
        if not key:
            if getattr(self, "environment", "production").lower() == "production":
                raise ValueError("ADMIN_JWT_SECRET is required in production and must be at least 32 characters.")
            if not hasattr(self, "_ephemeral_key"):
                log.warning(
                    "ADMIN_JWT_SECRET is not set. Generating ephemeral key for development session. "
                    "Tokens will invalidate if the process restarts. Set ADMIN_JWT_SECRET in .env."
                )
                self._ephemeral_key = secrets.token_hex(32)
            key = self._ephemeral_key
        elif len(key) < 32:
            raise ValueError("ADMIN_JWT_SECRET is too short (must be at least 32 characters).")
        return key.encode("utf-8")

    def get_google_client_id(self) -> str:
        """Returns the configured Google Client ID."""
        cid = self.google_client_id or os.environ.get("GOOGLE_CLIENT_ID") or ""
        return cid.strip()

    def validate_admin_auth_config(self) -> None:
        """
        Validates that required administrative authentication configurations are present.
        Called on application startup.
        """
        key = self.get_signing_key()
        if len(key) < 32:
            raise ValueError("ADMIN_JWT_SECRET must be at least 32 characters.")
        cid = self.get_google_client_id()
        if not cid:
            log.warning("GOOGLE_CLIENT_ID is not configured. Google admin authentication will be unavailable.")


settings = AdminSettings()
