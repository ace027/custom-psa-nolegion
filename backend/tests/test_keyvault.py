import json
import logging
import time

import httpx
import pytest

from app import keyvault
from app.config import Settings, get_settings
from app.errors import Conflict
from app.keyvault import KeyVault, KeyVaultError

VAULT = "https://psa-kv.vault.azure.net"
SECRET = "s3cr3t-value-never-shown"


@pytest.fixture
def identity(monkeypatch):
    monkeypatch.setenv("IDENTITY_ENDPOINT", "http://identity.local/msi/token")
    monkeypatch.setenv("IDENTITY_HEADER", "id-header-1")
    monkeypatch.setattr(get_settings(), "azure_client_id", "mi-client-1")


def make_vault(handler):
    calls: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "identity.local":
            return httpx.Response(
                200, json={"access_token": "kv-token", "expires_on": str(int(time.time()) + 3600)}
            )
        return handler(request)

    return KeyVault(VAULT, http=httpx.Client(transport=httpx.MockTransport(record))), calls


def test_set_secret_uses_managed_identity_and_puts_value(identity):
    vault, calls = make_vault(lambda r: httpx.Response(200, json={"id": "x"}))
    vault.set_secret("mail-client-secret", SECRET)
    vault.set_secret("portal-client-secret", SECRET)
    token_req, put, put2 = calls  # token cached across calls
    assert token_req.headers["X-IDENTITY-HEADER"] == "id-header-1"
    assert token_req.url.params["resource"] == "https://vault.azure.net"
    assert token_req.url.params["api-version"] == "2019-08-01"
    assert token_req.url.params["client_id"] == "mi-client-1"
    assert put.method == "PUT"
    assert str(put.url) == f"{VAULT}/secrets/mail-client-secret?api-version=7.4"
    assert put.headers["Authorization"] == "Bearer kv-token"
    assert json.loads(put.content) == {"value": SECRET, "contentType": "text/plain"}
    assert put2.url.path == "/secrets/portal-client-secret"


def test_token_refreshed_near_expiry(identity):
    vault, calls = make_vault(lambda r: httpx.Response(200, json={}))
    vault.set_secret("a", "v")
    vault._token_expires = time.time() + 30  # inside the 60 s margin
    vault.set_secret("b", "v")
    assert [c.url.host for c in calls].count("identity.local") == 2


def test_failure_never_exposes_value(identity, caplog):
    caplog.set_level(logging.DEBUG)
    vault, _ = make_vault(lambda r: httpx.Response(403, text=f"denied, you sent {SECRET}"))
    with pytest.raises(KeyVaultError) as exc:
        vault.set_secret("mail-client-secret", SECRET)
    assert SECRET not in str(exc.value) and "denied" not in str(exc.value)
    assert SECRET not in caplog.text
    ok, _ = make_vault(lambda r: httpx.Response(200, json={}))
    ok.set_secret("x", SECRET)
    assert SECRET not in caplog.text


def test_network_error_never_exposes_value(identity):
    def boom(request):
        raise httpx.ConnectError(f"cannot send {SECRET}")

    vault, _ = make_vault(boom)
    with pytest.raises(KeyVaultError) as exc:
        vault.set_secret("name", SECRET)
    assert SECRET not in str(exc.value)
    assert exc.value.__cause__ is None and exc.value.__suppress_context__  # no chained message


@pytest.mark.parametrize("name", ["", "Upper", "under_score", "a/b", "../x", "a" * 128, "x\n"])
def test_invalid_name_rejected_before_any_request(identity, name):
    vault, calls = make_vault(lambda r: httpx.Response(200))
    with pytest.raises(KeyVaultError, match="Invalid Key Vault secret name"):
        vault.set_secret(name, SECRET)
    assert calls == []


def test_secret_exists(identity):
    values = {"/secrets/real": "abc", "/secrets/placeholder": "unset"}

    def handler(request):
        if request.url.path in values:
            return httpx.Response(200, json={"value": values[request.url.path]})
        return httpx.Response(404, json={"error": {"code": "SecretNotFound"}})

    vault, _ = make_vault(handler)
    assert vault.secret_exists("real") is True
    assert vault.secret_exists("placeholder") is False
    assert vault.secret_exists("missing") is False


def test_secret_exists_raises_on_other_errors(identity):
    vault, _ = make_vault(lambda r: httpx.Response(500, text="oops"))
    with pytest.raises(KeyVaultError, match="HTTP 500"):
        vault.secret_exists("x")


def test_no_identity_endpoint(monkeypatch):
    monkeypatch.delenv("IDENTITY_ENDPOINT", raising=False)
    vault, _ = make_vault(lambda r: httpx.Response(200))
    with pytest.raises(KeyVaultError, match="Managed identity"):
        vault.set_secret("x", SECRET)


def test_from_settings_and_require_vault(monkeypatch):
    monkeypatch.setattr(get_settings(), "key_vault_url", "")
    assert KeyVault.from_settings() is None
    with pytest.raises(Conflict, match="Key Vault is not configured"):
        keyvault.require_vault()
    monkeypatch.setattr(get_settings(), "key_vault_url", VAULT + "/")
    assert keyvault.require_vault().vault_url == VAULT
    with pytest.raises(KeyVaultError, match="https"):
        KeyVault("http://psa-kv.vault.azure.net")


def test_config_maps_unset_to_empty(monkeypatch):
    monkeypatch.setenv("GRAPH_CLIENT_SECRET", "unset")
    monkeypatch.setenv("KEY_VAULT_URL", "unset")
    monkeypatch.setenv("ONBOARDING_ENABLED", "true")
    s = Settings()
    assert s.graph_client_secret == "" and s.key_vault_url == ""
    assert s.onboarding_enabled is True
    assert not s.mail_configured
    monkeypatch.setenv("GRAPH_CLIENT_SECRET", "real")
    assert Settings().graph_client_secret == "real"
