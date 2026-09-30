"""Settings come from environment variables only. Nothing secret lives in the repo."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"  # "production" disables dev login
    # App runtime connection: a NON-owner role so row-level security applies.
    database_url: str = "postgresql+psycopg://psa_app:app_dev@localhost:5432/psa"
    # Migrations run as the table owner.
    migration_database_url: str = "postgresql+psycopg://psa_owner:owner_dev@localhost:5432/psa"

    public_url: str = "http://localhost:8000"
    session_secret: str = "dev-only-change-me"  # signs the short-lived OIDC state cookie
    session_cookie_name: str = "psa_session"
    session_max_age_hours: int = 12

    entra_tenant_id: str = ""
    entra_client_id: str = ""
    entra_client_secret: str = ""

    dev_login_enabled: bool = False

    # Inbound/outbound mail (Microsoft Graph, application permissions scoped by Exchange RBAC to
    # ONE mailbox). Use a SEPARATE app registration from the sign-in one. See docs/MAIL_SETUP.md.
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    mail_mailbox: str = ""  # e.g. support@yourmsp.com
    # Sovereign clouds (e.g. GCC High): https://graph.microsoft.us and https://login.microsoftonline.us
    graph_base_url: str = "https://graph.microsoft.com/v1.0"
    graph_login_url: str = "https://login.microsoftonline.com"
    mail_poll_seconds: int = 60
    attachments_dir: str = "./data/attachments"
    max_attachment_bytes: int = 10 * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def mail_configured(self) -> bool:
        return bool(
            self.graph_tenant_id
            and self.graph_client_id
            and self.graph_client_secret
            and self.mail_mailbox
        )

    @property
    def entra_configured(self) -> bool:
        return bool(self.entra_tenant_id and self.entra_client_id and self.entra_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
