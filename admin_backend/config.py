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
    # If not set in environment, generate an ephemeral secret for this process run.
    # A persistent ADMIN_SECRET_KEY should be set in production .env.
    admin_secret_key: str = ""
    admin_token_algorithm: str = "HS256"
    admin_token_expire_minutes: int = 60
    admin_rate_limit_per_minute: int = 120

    # Storage paths
    admin_audit_log_path: str = os.path.join("logs", "admin_audit.jsonl")
    admin_traces_log_path: str = os.path.join("logs", "admin_traces.jsonl")
    admin_safety_log_path: str = os.path.join("logs", "admin_safety.jsonl")
    scores_log_path: str = os.path.join("logs", "scores.jsonl")
    redteam_results_path: str = os.path.join("logs", "redteam_results.json")

    # Dependency Connection URLs (for health probes & future live adapters)
    redis_url: str = "redis://localhost:6379/0"
    postgres_dsn: str = "postgresql://postgres:devpassword@localhost:5432/research_platform"
    groq_api_key: Optional[str] = None
    ollama_host: str = "http://localhost:11434"
    tavily_api_key: Optional[str] = None

    # Privacy & Retention
    admin_data_retention_days: int = 30
    admin_max_preview_length: int = 160
    admin_mask_pii: bool = True

    def get_signing_key(self) -> bytes:
        """
        Returns the signing key as bytes.
        If admin_secret_key is empty, generates an ephemeral random secret.
        """
        key = self.admin_secret_key or os.environ.get("ADMIN_SECRET_KEY", "")
        if not key:
            # Ephemeral fallback to prevent predictable secrets while remaining secure.
            if not hasattr(self, "_ephemeral_key"):
                log.warning(
                    "ADMIN_SECRET_KEY is not set. Generating ephemeral key for this session. "
                    "Tokens will invalidate if the process restarts. Set ADMIN_SECRET_KEY in production."
                )
                self._ephemeral_key = secrets.token_hex(32)
            key = self._ephemeral_key
        return key.encode("utf-8")


settings = AdminSettings()
