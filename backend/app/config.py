"""Settings come from environment variables only. Nothing secret lives in the repo."""

from functools import lru_cache

from pydantic import ValidationInfo, field_validator
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
    portal_cookie_name: str = "psa_portal"
    portal_session_hours: int = 8
    portal_link_minutes: int = 15

    entra_tenant_id: str = ""
    entra_client_id: str = ""
    entra_client_secret: str = ""
    # Client-portal SSO: a SECOND, multi-tenant app registration (authority "organizations"),
    # separate from the single-tenant staff one above. See docs/PORTAL_SSO.md.
    portal_entra_client_id: str = ""
    portal_entra_client_secret: str = ""

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
    # Per-client cap on files uploaded through the portal (sum of their sizes).
    portal_org_storage_bytes: int = 2 * 1024**3

    # Fernet key(s) protecting vendor API credentials stored in the database. Comma-separated for
    # rotation: the FIRST key encrypts, every key can decrypt. Generate with
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    credentials_key: str = ""

    # Outbound webhooks refuse private, loopback and link-local destinations (SSRF guard). Set
    # WEBHOOK_ALLOW_PRIVATE_HOSTS=true only to reach a LAN service such as a self-hosted n8n.
    webhook_allow_private_hosts: bool = False

    # Azure: the vault the onboarding wizard writes secrets to (via the managed identity whose
    # client id is AZURE_CLIENT_ID), and the switch that exposes the wizard routes at all.
    key_vault_url: str = ""
    azure_client_id: str = ""
    onboarding_enabled: bool = False

    @field_validator("*", mode="before")
    @classmethod
    def _unset_is_empty(cls, value, info: ValidationInfo):
        # deploy.sh pre-creates every wizard-managed Key Vault secret as the literal 'unset'
        # (Container Apps cannot reference a missing secret); it means "not configured".
        if value == "unset" and cls.model_fields[info.field_name].annotation is str:
            return ""
        return value

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

    @property
    def portal_sso_configured(self) -> bool:
        return bool(self.portal_entra_client_id and self.portal_entra_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
