import os
import logging
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("user_auth.config")

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ENV_FILE = os.path.join(_PROJECT_ROOT, ".env")


class UserAuthConfig(BaseSettings):
    google_client_id: Optional[str] = None
    session_cookie_name: str = "user_session"
    session_cookie_secure: bool = False
    session_cookie_max_age_days: int = 30
    require_login: bool = False
    auth_storage_backend: str = "postgres"  # "postgres" or "memory"
    neutralize_demo_users: bool = True
    trusted_proxy: bool = False
    allowed_auth_hosts: str = "localhost:8000,127.0.0.1:8000,localhost,127.0.0.1"

    # Advisory lock ID for migration 002 (Single constant across code and SQL)
    migration_advisory_lock_id: int = 742910482

    # Database
    postgres_dsn: str = "postgresql://postgres:devpassword@localhost:5432/research_platform"

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE if os.path.exists(_ENV_FILE) else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_allowed_hosts(self) -> List[str]:
        return [h.strip().lower() for h in self.allowed_auth_hosts.split(",") if h.strip()]


settings = UserAuthConfig()

log.info(
    "user_auth: GOOGLE_CLIENT_ID configured=%s, REQUIRE_LOGIN=%s, SESSION_COOKIE_SECURE=%s, AUTH_STORAGE_BACKEND=%s",
    bool(settings.google_client_id and settings.google_client_id.strip()),
    settings.require_login,
    settings.session_cookie_secure,
    settings.auth_storage_backend,
)
