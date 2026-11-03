"""Setup wizard steps (plan 19-03) against fake Microsoft Graph and Key Vault endpoints."""

import base64
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import unquote

import httpx
import pytest
from sqlalchemy import text

from app import crypto, onboarding
from app.config import get_settings
from app.keyvault import KeyVault

VAULT = "https://psa-kv.vault.azure.net"
SECRET = "fake-secretText-never-shown-9f8e7d"
TENANT = "11111111-2222-3333-4444-555555555555"
ADMIN_TOKEN = "eyJhbGciOiJub25lIn0.{}.sig".format(
    base64.urlsafe_b64encode(json.dumps({"tid": TENANT}).encode()).decode().rstrip("=")
)
GRAPH = "graph.microsoft.com"
PORTAL_ID = "aaaaaaaa-0000-0000-0000-000000000001"
MAIL_ID = "bbbbbbbb-0000-0000-0000-000000000002"
STAFF_SP = "staff-sp-object-id"
SCOPE_IDS = {"openid": "s-openid", "profile": "s-profile", "email": "s-email"}
ADMIN_SCOPES = "Application.ReadWrite.All AppRoleAssignment.ReadWrite.All "
ADMIN_SCOPES += "DelegatedPermissionGrant.ReadWrite.All"
REDIRECT = "http://localhost:8000/api/v1/portal/sso/callback"


class FakeMicrosoft:
    """Graph (admin token and app-only), login.microsoftonline.com, managed identity, Key Vault."""

    def __init__(self):
        self.calls: list[httpx.Request] = []
        self.apps: list[dict] = []
        self.sps: list[dict] = [
            {
                "id": "graph-sp",
                "appId": onboarding.GRAPH_APP_ID,
                "oauth2PermissionScopes": [
                    {"id": i, "value": v} for v, i in {**SCOPE_IDS, "User.Read": "s-ur"}.items()
                ],
            },
            {"id": STAFF_SP, "appId": "client-1"},
        ]
        self.grants: list[dict] = []
        self.vault: dict[str, str] = {}
        self.mailbox_status: dict[str, int] = {}  # GET /users/{u}/... for the app-only client
        self.force: dict[tuple[str, str], int] = {}  # (method, path) -> status

    def graph_posts(self) -> list[httpx.Request]:
        return [c for c in self.calls if c.url.host == GRAPH and c.method == "POST"]

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        host, method, path = request.url.host, request.method, request.url.path
        if host == "identity.local":
            exp = str(int(time.time()) + 3600)
            return httpx.Response(200, json={"access_token": "kv-token", "expires_on": exp})
        if host.endswith("vault.azure.net"):
            name = path.rsplit("/", 1)[-1]
            if method == "PUT":
                self.vault[name] = json.loads(request.content)["value"]
                return httpx.Response(200, json={"id": name})
            if name in self.vault:
                return httpx.Response(200, json={"value": self.vault[name]})
            return httpx.Response(404, json={"error": {"code": "SecretNotFound"}})
        if host == "login.microsoftonline.com":
            return httpx.Response(200, json={"access_token": "app-token", "expires_in": 3600})
        assert host == GRAPH, request.url
        path = path.removeprefix("/v1.0")
        if (method, path) in self.force:
            return httpx.Response(self.force[(method, path)], json={"error": {"code": "x"}})
        if path.startswith("/users/"):
            assert request.headers["Authorization"] == "Bearer app-token"
            user = unquote(path.split("/")[2])
            return httpx.Response(self.mailbox_status.get(user, 403), json={})
        assert request.headers["Authorization"] == f"Bearer {ADMIN_TOKEN}"
        filt = request.url.params.get("$filter", "")
        body = json.loads(request.content) if request.content else {}
        if path == "/applications" and method == "GET":
            field, _, value = filt.partition(" eq ")
            hits = [a for a in self.apps if a.get(field) == value.strip("'")]
            return httpx.Response(200, json={"value": hits})
        if path == "/applications" and method == "POST":
            n = len(self.apps) + 1
            app = {**body, "id": f"obj-{n}", "appId": f"0000000{n}-aaaa-bbbb-cccc-dddddddddddd"}
            self.apps.append(app)
            return httpx.Response(201, json=app)
        if path.endswith("/addPassword"):
            assert body["passwordCredential"]["displayName"] in ("psa-portal", "psa-mail")
            return httpx.Response(200, json={"secretText": SECRET, "keyId": "k"})
        if path == "/servicePrincipals" and method == "GET":
            value = filt.partition(" eq ")[2].strip("'")
            return httpx.Response(200, json={"value": [s for s in self.sps if s["appId"] == value]})
        if path == "/servicePrincipals" and method == "POST":
            sp = {"id": f"sp-{len(self.sps) + 1}", "appId": body["appId"]}
            self.sps.append(sp)
            return httpx.Response(201, json=sp)
        if path == "/oauth2PermissionGrants" and method == "GET":
            client = filt.partition(" eq ")[2].strip("'")
            return httpx.Response(
                200, json={"value": [g for g in self.grants if g["clientId"] == client]}
            )
        if path.startswith("/oauth2PermissionGrants/"):
            grant = next(g for g in self.grants if g["id"] == path.rsplit("/", 1)[-1])
            if method == "DELETE":
                self.grants.remove(grant)
                return httpx.Response(204)
            grant["scope"] = body["scope"]
            return httpx.Response(204)
        raise AssertionError(f"unexpected {method} {request.url}")


@pytest.fixture
def ms(monkeypatch):
    fake = FakeMicrosoft()
    s = get_settings()
    monkeypatch.setattr(s, "onboarding_enabled", True)
    monkeypatch.setattr(s, "key_vault_url", VAULT)
    monkeypatch.setenv("IDENTITY_ENDPOINT", "http://identity.local/msi/token")
    monkeypatch.setenv("IDENTITY_HEADER", "h")

    def client():
        return httpx.Client(transport=httpx.MockTransport(fake.handler))

    monkeypatch.setattr(onboarding, "_http_client", client)
    monkeypatch.setattr(KeyVault, "from_settings", classmethod(lambda cls: cls(VAULT, client())))
    return fake


@pytest.fixture
def consented(admin, owner):
    owner.execute(
        text(
            "INSERT INTO onboarding_tokens (user_id, token_ciphertext, scopes, expires_at) "
            "VALUES (:u, :c, 'x', :e)"
        ),
        {
            "u": admin.user["id"],
            "c": crypto.encrypt_credentials({"access_token": ADMIN_TOKEN}),
            "e": datetime.now(UTC) + timedelta(minutes=30),
        },
    )
    return admin


def audits(owner) -> list:
    return owner.execute(
        text("SELECT action, detail::text AS d FROM audit_log WHERE action LIKE 'onboarding.%'")
    ).all()


# ---- create ----


def test_create_portal_app_least_privilege_secret_only_in_vault(ms, consented, owner, caplog):
    caplog.set_level(logging.DEBUG)
    r = consented.post("/api/v1/onboarding/portal-app")
    assert r.status_code == 200, r.text
    (app,) = ms.apps
    assert r.json() == {"app_id": app["appId"], "created": True}
    assert app["signInAudience"] == "AzureADMultipleOrgs"
    assert app["web"]["redirectUris"] == [REDIRECT]
    (graph,) = app["requiredResourceAccess"]
    assert graph["resourceAppId"] == onboarding.GRAPH_APP_ID
    assert sorted(a["id"] for a in graph["resourceAccess"]) == sorted(SCOPE_IDS.values())
    assert {a["type"] for a in graph["resourceAccess"]} == {"Scope"}
    assert ms.vault == {
        "portal-entra-client-secret": SECRET,
        "portal-entra-client-id": app["appId"],
    }
    assert [a.action for a in audits(owner)] == ["onboarding.portal_app_created"]
    assert SECRET not in r.text and SECRET not in caplog.text
    assert all(SECRET not in (a.d or "") for a in audits(owner))


def test_create_mail_app_no_permissions_and_powershell(ms, consented, owner, caplog):
    caplog.set_level(logging.DEBUG)
    r = consented.post("/api/v1/onboarding/mail-app", json={"mailbox": "Support@Example.com"})
    assert r.status_code == 200, r.text
    (app,) = ms.apps
    body = r.json()
    assert "requiredResourceAccess" not in app and app["signInAudience"] == "AzureADMyOrg"
    sp = body["service_principal_object_id"]
    assert body["app_id"] == app["appId"] and sp == ms.sps[-1]["id"]
    ps = body["powershell"]
    assert f"New-ServicePrincipal -AppId {app['appId']} -ObjectId {sp}" in ps
    assert "PrimarySmtpAddress -eq 'support@example.com'" in ps
    for role in ("Mail.ReadWrite", "Mail.Send", "Calendars.ReadWrite"):
        assert f'-App {sp} -Role "Application {role}"' in ps
    assert ms.vault == {
        "graph-client-secret": SECRET,
        "graph-client-id": app["appId"],
        "graph-tenant-id": TENANT,
        "mail-mailbox": "support@example.com",
    }
    assert SECRET not in r.text and SECRET not in caplog.text
    assert all(SECRET not in (a.d or "") for a in audits(owner))
    assert [a.action for a in audits(owner)] == ["onboarding.mail_app_created"]


def test_create_mail_app_rejects_powershell_metacharacters(ms, consented):
    r = consented.post("/api/v1/onboarding/mail-app", json={"mailbox": "a'b@example.com"})
    assert r.status_code == 422
    assert ms.calls == []


def test_create_without_key_vault_refused_before_graph(ms, consented, monkeypatch):
    monkeypatch.setattr(KeyVault, "from_settings", classmethod(lambda cls: None))
    for path, body in (("portal-app", None), ("mail-app", {"mailbox": "s@example.com"})):
        r = consented.post(f"/api/v1/onboarding/{path}", json=body)
        assert r.status_code == 409 and r.json()["detail"] == "Key Vault is not configured"
    assert ms.graph_posts() == []


def test_create_existing_name_offers_connect(ms, consented):
    ms.apps.append({"id": "obj-x", "appId": PORTAL_ID, "displayName": "PSA Client Portal"})
    r = consented.post("/api/v1/onboarding/portal-app")
    assert r.status_code == 409 and r.json()["app_id"] == PORTAL_ID
    assert ms.graph_posts() == [] and ms.vault == {}


@pytest.mark.parametrize(
    ("status", "code", "message"),
    [
        (429, 503, "Microsoft is busy, try again in a minute"),
        (403, 403, "Your account cannot create app registrations"),
    ],
)
def test_create_graph_errors_public_message(ms, consented, status, code, message):
    ms.force[("POST", "/applications")] = status
    r = consented.post("/api/v1/onboarding/portal-app")
    assert r.status_code == code and r.json() == {"detail": message}


def test_create_without_consent_asks_to_sign_in(ms, admin):
    r = admin.post("/api/v1/onboarding/portal-app")
    assert r.status_code == 409 and "Sign in to Microsoft again" in r.json()["detail"]


# ---- connect ----


def test_connect_reports_extra_permissions_and_stores_nothing(ms, consented):
    ms.apps.append(
        {
            "id": "obj-m",
            "appId": MAIL_ID,
            "requiredResourceAccess": [
                {
                    "resourceAppId": onboarding.GRAPH_APP_ID,
                    "resourceAccess": [{"id": "mail-rw-role", "type": "Role"}],
                }
            ],
        }
    )
    r = consented.post("/api/v1/onboarding/connect", json={"kind": "mail", "app_id": MAIL_ID})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["connected"] is False and body["secret_created"] is False
    assert "application permissions" in body["differences"][0]
    assert ms.vault == {} and not any(c.url.path.endswith("addPassword") for c in ms.calls)


def test_connect_portal_reports_scope_and_redirect_differences(ms, consented):
    ms.apps.append(
        {
            "id": "obj-p",
            "appId": PORTAL_ID,
            "signInAudience": "AzureADMultipleOrgs",
            "web": {"redirectUris": []},
            "requiredResourceAccess": [
                {
                    "resourceAppId": onboarding.GRAPH_APP_ID,
                    "resourceAccess": [
                        {"id": "s-openid", "type": "Scope"},
                        {"id": "s-ur", "type": "Scope"},
                    ],
                }
            ],
        }
    )
    r = consented.post("/api/v1/onboarding/connect", json={"kind": "portal", "app_id": PORTAL_ID})
    diffs = r.json()["differences"]
    assert any(REDIRECT in d for d in diffs)
    assert any("beyond openid" in d for d in diffs)
    assert any("email, profile" in d for d in diffs)
    assert r.json()["connected"] is False


def test_connect_matching_app_creates_secret(ms, consented, owner, caplog):
    caplog.set_level(logging.DEBUG)
    ms.apps.append({"id": "obj-m", "appId": MAIL_ID, "signInAudience": "AzureADMyOrg"})
    r = consented.post(
        "/api/v1/onboarding/connect",
        json={"kind": "mail", "app_id": MAIL_ID.upper(), "mailbox": "support@example.com"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["connected"] and body["secret_created"] and body["differences"] == []
    assert MAIL_ID in body["powershell"]
    assert ms.vault["graph-client-secret"] == SECRET and ms.vault["graph-client-id"] == MAIL_ID
    assert SECRET not in r.text and SECRET not in caplog.text
    assert [a.action for a in audits(owner)] == ["onboarding.app_connected"]


def test_connect_rejects_non_guid(ms, consented):
    r = consented.post("/api/v1/onboarding/connect", json={"kind": "mail", "app_id": "x' or 1"})
    assert r.status_code == 422 and ms.calls == []


# ---- verify ----


def steps(client) -> dict:
    r = client.get("/api/v1/onboarding/status")
    assert r.status_code == 200, r.text
    return {s["step"]: s for s in r.json()["steps"]}


@pytest.fixture
def mail_running(monkeypatch):
    s = get_settings()
    for name, value in {
        "graph_tenant_id": TENANT,
        "graph_client_id": MAIL_ID,
        "graph_client_secret": "running-secret",
        "mail_mailbox": "support@example.com",
    }.items():
        monkeypatch.setattr(s, name, value)


def test_verify_mail_scoped_ok(ms, admin, mail_running, make_user):
    make_user("tech", "tech1@example.com")
    ms.mailbox_status.update({"support@example.com": 200, "tech1@example.com": 200})
    got = steps(admin)
    assert got["staff_sso"]["status"] == "ok"
    assert got["mail"]["status"] == "ok"
    assert got["calendar"]["status"] == "ok" and "tech1@example.com" in got["calendar"]["message"]
    assert got["portal_sso"]["status"] == "missing"


def test_verify_mail_out_of_scope_mailbox_readable_is_error(ms, admin, mail_running):
    ms.mailbox_status.update({"support@example.com": 200, "admin@example.com": 200})
    mail = steps(admin)["mail"]
    assert mail["status"] == "error"
    assert mail["message"] == (
        "The mail app can read mailboxes outside its scope: run the scope commands"
    )


def test_verify_restart_needed_when_only_in_vault(ms, admin):
    ms.vault.update({"graph-client-secret": "v", "portal-entra-client-secret": "unset"})
    got = steps(admin)
    assert got["mail"]["status"] == "restart_needed"
    assert "az containerapp revision restart" in got["mail"]["message"]
    assert got["calendar"]["status"] == "restart_needed"
    assert got["portal_sso"]["status"] == "missing"  # the deploy placeholder is not a value


def test_verify_portal_checks_app_with_admin_token(ms, consented, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "portal_entra_client_id", PORTAL_ID)
    monkeypatch.setattr(s, "portal_entra_client_secret", "running")
    assert steps(consented)["portal_sso"]["status"] == "error"  # app gone
    ms.apps.append({"id": "o", "appId": PORTAL_ID, "web": {"redirectUris": [REDIRECT]}})
    assert steps(consented)["portal_sso"]["status"] == "ok"


# ---- finish ----


def test_finish_removes_only_admin_scopes_and_token(ms, consented, owner):
    ms.grants = [
        {"id": "g1", "clientId": STAFF_SP, "scope": f"openid profile User.Read {ADMIN_SCOPES}"},
        {"id": "g2", "clientId": STAFF_SP, "scope": ADMIN_SCOPES},
        {"id": "g3", "clientId": "other-sp", "scope": ADMIN_SCOPES},
    ]
    r = consented.post("/api/v1/onboarding/finish")
    assert r.status_code == 200, r.text
    assert r.json()["removed_scopes"] == sorted(ADMIN_SCOPES.split())
    assert {g["id"]: g["scope"] for g in ms.grants} == {
        "g1": "openid profile User.Read",
        "g3": ADMIN_SCOPES,
    }
    assert owner.execute(text("SELECT count(*) FROM onboarding_tokens")).scalar_one() == 0
    assert [a.action for a in audits(owner)] == ["onboarding.finished"]
    assert ADMIN_TOKEN not in r.text


# ---- guard ----

ROUTES = [
    ("GET", "/api/v1/onboarding/status", None),
    ("POST", "/api/v1/onboarding/portal-app", None),
    ("POST", "/api/v1/onboarding/mail-app", {"mailbox": "s@example.com"}),
    ("POST", "/api/v1/onboarding/connect", {"kind": "mail", "app_id": MAIL_ID}),
    ("POST", "/api/v1/onboarding/finish", None),
]


@pytest.mark.parametrize("role", ["tech", "manager", "billing"])
def test_non_admin_forbidden_on_every_route(ms, login, role):
    client = login(role)
    for method, path, body in ROUTES:
        assert client.request(method, path, json=body).status_code == 403, path
    assert ms.calls == []


def test_disabled_returns_404(admin, monkeypatch):
    monkeypatch.setattr(get_settings(), "onboarding_enabled", False)
    for method, path, body in ROUTES:
        assert admin.request(method, path, json=body).status_code == 404, path
