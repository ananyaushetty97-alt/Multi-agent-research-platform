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

    # Email Verification & Delivery
    verify_email_dns: bool = True
    block_disposable_emails: bool = True
    otp_expiry_minutes: int = 10
    otp_resend_cooldown_seconds: int = 60
    otp_max_attempts: int = 5
    reset_token_expiry_minutes: int = 30
    app_base_url: str = "http://localhost:8000"

    # SMTP & Email Delivery Configuration
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: str = "noreply@platform.ai"
    smtp_tls: bool = True
    smtp_timeout_seconds: int = 5

    # HTTPS Email APIs (bypass ISP raw SMTP port blocks)
    resend_api_key: Optional[str] = None
    resend_from: str = "Research Hub <onboarding@resend.dev>"
    brevo_api_key: Optional[str] = None
    brevo_from: Optional[str] = None

    @property
    def email_configured(self) -> bool:
        """Returns True if any production email provider (SMTP or HTTPS API) is configured."""
        if self.resend_api_key and self.resend_api_key.strip():
            return True
        if self.brevo_api_key and self.brevo_api_key.strip():
            return True
        if self.smtp_host and self.smtp_host.strip():
            return True
        return False

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
    "user_auth: GOOGLE_CLIENT_ID configured=%s, REQUIRE_LOGIN=%s, SESSION_COOKIE_SECURE=%s, AUTH_STORAGE_BACKEND=%s, SMTP configured=%s, EMAIL configured=%s",
    bool(settings.google_client_id and settings.google_client_id.strip()),
    settings.require_login,
    settings.session_cookie_secure,
    settings.auth_storage_backend,
    bool(settings.smtp_host),
    settings.email_configured,
)
