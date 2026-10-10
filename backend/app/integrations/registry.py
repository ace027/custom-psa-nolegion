"""Builds an adapter from a stored integration. Tests replace `build_adapter` with a fake."""

from app import crypto
from app.integrations.base import Adapter, VendorError
from app.integrations.hudu import HuduClient
from app.integrations.ninjaone import NinjaOneClient
from app.models import Integration

CREDENTIAL_FIELDS = {
    "ninjaone": ("client_id", "client_secret"),
    "hudu": ("api_key",),
}


def build_adapter(integration: Integration) -> Adapter:
    if not integration.credentials:
        raise VendorError("no credentials have been set")
    try:
        creds = crypto.decrypt_credentials(integration.credentials)
    except crypto.CredentialsKeyError as exc:
        raise VendorError(str(exc)) from exc
    if integration.kind == "ninjaone":
        return NinjaOneClient(integration.base_url, creds["client_id"], creds["client_secret"])
    return HuduClient(integration.base_url, creds["api_key"], integration.config)
