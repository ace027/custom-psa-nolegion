"""Write secrets to Azure Key Vault with the app's managed identity (REST API, no Azure SDK).

Secret values exist only in local variables for the PUT: they are never logged, returned, put in
exception messages or chained into tracebacks. Error messages name the secret, never its value
and never the Key Vault response body.
"""

import logging
import os
import re
import time

import httpx

from app.config import get_settings
from app.errors import Conflict

logger = logging.getLogger(__name__)

API_VERSION = "7.4"
VAULT_RESOURCE = "https://vault.azure.net"
NAME_RE = re.compile(r"[a-z0-9-]{1,127}")
PLACEHOLDER = "unset"  # deploy.sh pre-creates wizard-managed secrets with this value


class KeyVaultError(RuntimeError):
    """Public message only: never contains a secret value or a response body."""


class KeyVault:
    def __init__(self, vault_url: str, http: httpx.Client | None = None):
        if not vault_url.startswith("https://"):
            raise KeyVaultError("KEY_VAULT_URL must be an https URL")
        self.vault_url = vault_url.rstrip("/")
        self._http = http or httpx.Client(timeout=15, follow_redirects=False)
        self._token: str | None = None
        self._token_expires = 0.0

    @classmethod
    def from_settings(cls) -> "KeyVault | None":
        url = get_settings().key_vault_url
        return cls(url) if url else None

    def _access_token(self) -> str:
        """Managed identity token for Key Vault, cached until 60 s before it expires."""
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        endpoint = os.environ.get("IDENTITY_ENDPOINT")
        header = os.environ.get("IDENTITY_HEADER")
        if not endpoint or not header:
            raise KeyVaultError("Managed identity is not available (IDENTITY_ENDPOINT not set)")
        params = {"resource": VAULT_RESOURCE, "api-version": "2019-08-01"}
        client_id = get_settings().azure_client_id
        if client_id:  # user-assigned identity; empty means the system-assigned one
            params["client_id"] = client_id
        try:
            r = self._http.get(endpoint, params=params, headers={"X-IDENTITY-HEADER": header})
        except httpx.HTTPError as exc:
            raise KeyVaultError(
                f"Managed identity token request failed: {type(exc).__name__}"
            ) from None
        if r.status_code != 200:
            raise KeyVaultError(f"Managed identity token request failed (HTTP {r.status_code})")
        body = r.json()
        self._token = body["access_token"]
        if body.get("expires_on"):
            self._token_expires = float(body["expires_on"])
        else:
            self._token_expires = time.time() + float(body.get("expires_in", 300))
        return self._token

    def _secret_url(self, name: str) -> str:
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            raise KeyVaultError("Invalid Key Vault secret name")
        return f"{self.vault_url}/secrets/{name}"

    def _request(self, method: str, name: str, **kw) -> httpx.Response:
        url = self._secret_url(name)
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        try:
            return self._http.request(
                method, url, params={"api-version": API_VERSION}, headers=headers, **kw
            )
        except httpx.HTTPError as exc:
            logger.warning("key vault %s %s failed: %s", method, name, type(exc).__name__)
            raise KeyVaultError(f"Key Vault request for secret '{name}' failed") from None

    def set_secret(self, name: str, value: str) -> None:
        r = self._request("PUT", name, json={"value": value, "contentType": "text/plain"})
        if not 200 <= r.status_code < 300:
            logger.warning("key vault PUT %s failed: HTTP %s", name, r.status_code)
            raise KeyVaultError(f"Key Vault write of secret '{name}' failed (HTTP {r.status_code})")
        logger.info("key vault secret %s written", name)

    def secret_exists(self, name: str) -> bool:
        """True when the secret holds a real value (not missing, empty or the placeholder)."""
        r = self._request("GET", name)
        if r.status_code == 404:
            return False
        if not 200 <= r.status_code < 300:
            logger.warning("key vault GET %s failed: HTTP %s", name, r.status_code)
            raise KeyVaultError(f"Key Vault read of secret '{name}' failed (HTTP {r.status_code})")
        value = r.json().get("value")
        return bool(value) and value != PLACEHOLDER


def require_vault() -> KeyVault:
    """For wizard steps that store secrets: 409 when no vault is configured."""
    vault = KeyVault.from_settings()
    if vault is None:
        raise Conflict("Key Vault is not configured")
    return vault
