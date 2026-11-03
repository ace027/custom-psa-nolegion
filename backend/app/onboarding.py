"""Setup wizard steps (plan 19-03): create or connect the portal SSO and Mail & Calendar app
registrations, verify every registration, and revoke the admin consent when done.

Graph calls use the admin's one-time consent token (app/onboarding_auth.py). A new client secret
(`secretText`) lives only in a local variable on its way to Key Vault: it is never returned,
logged, audited or put in an exception message. Errors carry a short public message only.
"""

import base64
import json
import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

import httpx
from fastapi import HTTPException
from sqlalchemy import select

from app import audit, onboarding_auth
from app.config import get_settings
from app.deps import Ctx
from app.errors import Conflict
from app.keyvault import KeyVault, KeyVaultError, require_vault
from app.mail.graph import GraphClient, GraphError
from app.models import User

logger = logging.getLogger(__name__)

GRAPH_APP_ID = "00000003-0000-0000-c000-000000000000"  # Microsoft Graph
PORTAL_SCOPES = ("openid", "profile", "email")
ADMIN_SCOPE_NAMES = tuple(s.rsplit("/", 1)[-1] for s in onboarding_auth.ADMIN_SCOPES.split())
PORTAL_NAME = "PSA Client Portal"
MAIL_NAME = "PSA Mail"
BUSY = "Microsoft is busy, try again in a minute"
NO_ROLE = "Your account cannot create app registrations"
RESTART = (
    "Restart the api and worker so they read the new values: "
    'for app in api worker; do az containerapp revision restart -g "$RESOURCE_GROUP" -n "$app" '
    '--revision "$(az containerapp revision list -g "$RESOURCE_GROUP" -n "$app" '
    '--query "[?properties.active].name | [0]" -o tsv)"; done'
)


class OnboardingError(HTTPException):
    """`detail` is the public message: never a secret, token or Graph response body."""


class AppExists(OnboardingError):
    def __init__(self, display_name: str, app_id: str):
        super().__init__(
            409, f"An app named '{display_name}' already exists: connect it instead of creating one"
        )
        self.app_id = app_id


def _http_client() -> httpx.Client:
    return httpx.Client(timeout=30, follow_redirects=False)


def _graph(token: str, method: str, path: str, **kw) -> dict:
    """One Graph call with the admin token; JSON body ({} when empty) or OnboardingError."""
    url = f"{get_settings().graph_base_url.rstrip('/')}{path}"
    try:
        with _http_client() as http:
            r = http.request(method, url, headers={"Authorization": f"Bearer {token}"}, **kw)
    except httpx.HTTPError as exc:
        logger.warning("onboarding graph %s %s failed: %s", method, path, type(exc).__name__)
        raise OnboardingError(502, "Microsoft Graph is unreachable, try again") from None
    if r.status_code >= 400:
        logger.warning("onboarding graph %s %s: HTTP %s", method, path, r.status_code)
        if r.status_code == 429:
            raise OnboardingError(503, BUSY)
        if r.status_code == 401:
            raise Conflict(onboarding_auth.EXPIRED_MESSAGE)
        if r.status_code == 403:
            raise OnboardingError(403, NO_ROLE)
        raise OnboardingError(502, f"Microsoft Graph request failed (HTTP {r.status_code})")
    return r.json() if r.content else {}


def _odata(value: str) -> str:
    return quote(value.replace("'", "''"), safe="")


def _find_app(token: str, *, app_id: str | None = None, name: str | None = None) -> dict | None:
    field, value = ("appId", app_id) if app_id else ("displayName", name)
    found = _graph(token, "GET", f"/applications?$filter={field} eq '{_odata(value)}'")
    return (found.get("value") or [None])[0]


def _service_principal(token: str, app_id: str) -> dict | None:
    found = _graph(token, "GET", f"/servicePrincipals?$filter=appId eq '{_odata(app_id)}'")
    return (found.get("value") or [None])[0]


def _portal_scope_ids(token: str) -> dict[str, str]:
    """openid/profile/email delegated scope ids, read from the Graph service principal."""
    sp = _service_principal(token, GRAPH_APP_ID) or {}
    ids = {s["value"]: s["id"] for s in sp.get("oauth2PermissionScopes", []) if "value" in s}
    if any(name not in ids for name in PORTAL_SCOPES):
        raise OnboardingError(502, "Microsoft Graph did not list the openid, profile and email")
    return {name: ids[name] for name in PORTAL_SCOPES}


def _tenant_id(token: str) -> str:
    """The tid claim, read WITHOUT verifying the token: only to name the tenant, never for auth."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        tid = claims["tid"]
    except (IndexError, KeyError, ValueError, TypeError):
        raise OnboardingError(
            502, "Could not read the tenant id from the Microsoft token"
        ) from None
    if not isinstance(tid, str) or not tid:
        raise OnboardingError(502, "Could not read the tenant id from the Microsoft token")
    return tid


def _new_secret_to_vault(
    token: str,
    vault: KeyVault,
    object_id: str,
    label: str,
    secret_name: str,
    values: dict[str, str],
) -> None:
    """addPassword, then write the secretText and the other values to Key Vault."""
    end = (datetime.now(UTC) + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
    created = _graph(
        token,
        "POST",
        f"/applications/{object_id}/addPassword",
        json={"passwordCredential": {"displayName": label, "endDateTime": end}},
    )
    secret_text = created.get("secretText")
    if not secret_text:
        raise OnboardingError(502, "Microsoft did not return a client secret")
    try:
        vault.set_secret(secret_name, secret_text)
        for name, value in values.items():
            vault.set_secret(name, value)
    except KeyVaultError as exc:  # its message names the secret, never the value
        raise OnboardingError(502, str(exc)) from None


def _create_app(token: str, body: dict) -> tuple[dict, dict]:
    existing = _find_app(token, name=body["displayName"])
    if existing:
        raise AppExists(body["displayName"], existing["appId"])
    app = _graph(token, "POST", "/applications", json=body)
    sp = _graph(token, "POST", "/servicePrincipals", json={"appId": app["appId"]})
    return app, sp


def _portal_redirect() -> str:
    return f"{get_settings().public_url}/api/v1/portal/sso/callback"


def create_portal_app(ctx: Ctx, display_name: str = PORTAL_NAME) -> dict:
    vault = require_vault()  # before anything is created in the tenant
    token = onboarding_auth.get_admin_token(ctx)
    scopes = _portal_scope_ids(token)
    app, _ = _create_app(
        token,
        {
            "displayName": display_name,
            "signInAudience": "AzureADMultipleOrgs",
            "web": {"redirectUris": [_portal_redirect()]},
            "requiredResourceAccess": [
                {
                    "resourceAppId": GRAPH_APP_ID,
                    "resourceAccess": [{"id": i, "type": "Scope"} for i in scopes.values()],
                }
            ],
        },
    )
    _new_secret_to_vault(
        token,
        vault,
        app["id"],
        "psa-portal",
        "portal-entra-client-secret",
        {"portal-entra-client-id": app["appId"]},
    )
    audit.record(ctx.db, ctx.user, "onboarding.portal_app_created", detail={"app_id": app["appId"]})
    return {"app_id": app["appId"], "created": True}


def powershell(app_id: str, sp_object_id: str, mailbox: str) -> str:
    """docs/MAIL_SETUP.md section 3 and docs/CALENDAR_SETUP.md section 2, filled in."""
    return f"""Connect-ExchangeOnline

# Exchange's pointer to the Entra service principal
New-ServicePrincipal -AppId {app_id} -ObjectId {sp_object_id} -DisplayName "PSA Mail"

# The set of mailboxes the app may touch: exactly one
New-ManagementScope -Name "PSA Support Mailbox" `
  -RecipientRestrictionFilter "PrimarySmtpAddress -eq '{mailbox}'"

# Read/update/mark-read mail, and send mail, both limited to that scope
New-ManagementRoleAssignment -App {sp_object_id} -Role "Application Mail.ReadWrite" `
  -CustomResourceScope "PSA Support Mailbox"
New-ManagementRoleAssignment -App {sp_object_id} -Role "Application Mail.Send" `
  -CustomResourceScope "PSA Support Mailbox"

$group = Get-DistributionGroup "PSA Techs"

# The set of mailboxes the app may touch: members of the group
New-ManagementScope -Name "PSA Techs Calendars" `
  -RecipientRestrictionFilter "MemberOfGroup -eq '$($group.DistinguishedName)'"

# Read and write calendars (events and getSchedule), limited to that scope
New-ManagementRoleAssignment -App {sp_object_id} -Role "Application Calendars.ReadWrite" `
  -CustomResourceScope "PSA Techs Calendars"
"""


def create_mail_app(ctx: Ctx, mailbox: str) -> dict:
    vault = require_vault()
    token = onboarding_auth.get_admin_token(ctx)
    tenant = _tenant_id(token)
    # Single tenant and NO requiredResourceAccess: Entra permissions are tenant-wide and would
    # cancel the Exchange RBAC mailbox scoping (docs/MAIL_SETUP.md section 2).
    app, sp = _create_app(token, {"displayName": MAIL_NAME, "signInAudience": "AzureADMyOrg"})
    _new_secret_to_vault(
        token,
        vault,
        app["id"],
        "psa-mail",
        "graph-client-secret",
        {"graph-client-id": app["appId"], "graph-tenant-id": tenant, "mail-mailbox": mailbox},
    )
    audit.record(
        ctx.db,
        ctx.user,
        "onboarding.mail_app_created",
        detail={"app_id": app["appId"], "service_principal_object_id": sp["id"]},
    )
    return {
        "app_id": app["appId"],
        "service_principal_object_id": sp["id"],
        "created": True,
        "powershell": powershell(app["appId"], sp["id"], mailbox),
    }


def _graph_resources(app: dict) -> list[dict]:
    return [r for r in app.get("requiredResourceAccess") or [] if r.get("resourceAppId")]


def _mail_differences(app: dict) -> list[str]:
    out = []
    for r in _graph_resources(app):
        if any(a.get("type") == "Role" for a in r.get("resourceAccess") or []):
            which = "Microsoft Graph" if r["resourceAppId"] == GRAPH_APP_ID else "API"
            out.append(
                f"Remove the {which} application permissions: "
                "they apply to every mailbox and cancel the Exchange scoping"
            )
    return out


def _portal_differences(app: dict, token: str) -> list[str]:
    out = []
    if app.get("signInAudience") != "AzureADMultipleOrgs":
        out.append("Set the supported account types to any organizational directory")
    if _portal_redirect() not in ((app.get("web") or {}).get("redirectUris") or []):
        out.append(f"Add the web redirect URI {_portal_redirect()}")
    wanted = {i: name for name, i in _portal_scope_ids(token).items()}
    have = {
        (r["resourceAppId"], a.get("id"), a.get("type"))
        for r in _graph_resources(app)
        for a in r.get("resourceAccess") or []
    }
    extra = [h for h in have if not (h[0] == GRAPH_APP_ID and h[2] == "Scope" and h[1] in wanted)]
    if extra:
        out.append(f"Remove the {len(extra)} API permission(s) beyond openid, profile and email")
    missing = sorted(n for i, n in wanted.items() if (GRAPH_APP_ID, i, "Scope") not in have)
    if missing:
        out.append(f"Add the delegated Microsoft Graph permission(s) {', '.join(missing)}")
    return out


def connect_existing(ctx: Ctx, kind: str, app_id: str, mailbox: str | None = None) -> dict:
    """Connect an existing registration. A secret is only made when it matches least privilege
    and the running config does not already use this app with a secret."""
    s = get_settings()
    vault = require_vault()
    token = onboarding_auth.get_admin_token(ctx)
    app = _find_app(token, app_id=app_id)
    if app is None:
        raise OnboardingError(404, "No app registration with that application id")
    sp = _service_principal(token, app_id)
    out = {
        "kind": kind,
        "app_id": app_id,
        "differences": (
            _portal_differences(app, token) if kind == "portal" else _mail_differences(app)
        ),
        "connected": False,
        "secret_created": False,
        "service_principal_object_id": sp["id"] if sp else None,
        "powershell": None,
    }
    if out["differences"]:
        return out  # least privilege first: nothing is stored until the app is fixed
    if sp is None:
        sp = _graph(token, "POST", "/servicePrincipals", json={"appId": app_id})
        out["service_principal_object_id"] = sp["id"]
    if kind == "portal":
        in_use = s.portal_entra_client_id == app_id and bool(s.portal_entra_client_secret)
        values, secret_name, label = (
            {"portal-entra-client-id": app_id},
            "portal-entra-client-secret",
            "psa-portal",
        )
    else:
        mailbox = mailbox or s.mail_mailbox
        in_use = s.graph_client_id == app_id and bool(s.graph_client_secret)
        values = {"graph-client-id": app_id, "graph-tenant-id": _tenant_id(token)}
        if mailbox:
            values["mail-mailbox"] = mailbox
            out["powershell"] = powershell(app_id, sp["id"], mailbox)
        secret_name, label = "graph-client-secret", "psa-mail"
    if not in_use:
        _new_secret_to_vault(token, vault, app["id"], label, secret_name, values)
        out["secret_created"] = True
    out["connected"] = True
    audit.record(
        ctx.db,
        ctx.user,
        "onboarding.app_connected",
        detail={"kind": kind, "app_id": app_id, "secret_created": out["secret_created"]},
    )
    return out


def _step(step: str, status: str, message: str) -> dict:
    return {"step": step, "status": status, "message": message}


def _not_running(vault: KeyVault | None, step: str, secret_name: str, what: str) -> dict:
    """Missing from the running config: restart_needed when Key Vault already holds it."""
    try:
        if vault is not None and vault.secret_exists(secret_name):
            return _step(step, "restart_needed", f"{what} is saved in Key Vault. {RESTART}")
    except KeyVaultError as exc:
        return _step(step, "error", str(exc))
    return _step(step, "missing", f"{what} is not set up yet")


def _check_portal(ctx: Ctx, vault: KeyVault | None) -> dict:
    s = get_settings()
    if not s.portal_sso_configured:
        return _not_running(
            vault, "portal_sso", "portal-entra-client-secret", "Client portal sign-in"
        )
    try:
        token = onboarding_auth.get_admin_token(ctx)
    except Conflict:  # no admin token: the running config is all we can check
        return _step("portal_sso", "ok", "Client portal sign-in is configured")
    try:
        app = _find_app(token, app_id=s.portal_entra_client_id)
    except HTTPException as exc:
        return _step("portal_sso", "error", exc.detail)
    except Conflict as exc:
        return _step("portal_sso", "error", str(exc))
    if app is None:
        return _step("portal_sso", "error", "The portal app registration no longer exists")
    if _portal_redirect() not in ((app.get("web") or {}).get("redirectUris") or []):
        return _step(
            "portal_sso", "error", f"The portal app lacks the redirect {_portal_redirect()}"
        )
    return _step("portal_sso", "ok", "Client portal sign-in is configured")


def _mail_status(client: GraphClient, user: str, path: str) -> int:
    try:
        client._request_user(user, "GET", path)
    except GraphError as exc:
        if exc.status is None:
            raise
        return exc.status
    return 200


def _check_mail_and_calendar(ctx: Ctx, vault: KeyVault | None) -> list[dict]:
    s = get_settings()
    if not s.mail_configured:
        return [
            _not_running(vault, "mail", "graph-client-secret", "Mail"),
            _not_running(vault, "calendar", "graph-client-secret", "Calendar"),
        ]
    http = _http_client()
    client = GraphClient(
        s.graph_tenant_id,
        s.graph_client_id,
        s.graph_client_secret,
        s.mail_mailbox,
        http=http,
        base_url=s.graph_base_url,
        login_url=s.graph_login_url,
    )
    try:
        inbox = _mail_status(client, s.mail_mailbox, "/mailFolders/inbox")
        if inbox == 429:
            mail = _step("mail", "error", BUSY)
        elif inbox != 200:
            mail = _step(
                "mail",
                "error",
                f"The mail app cannot read {s.mail_mailbox} (HTTP {inbox}): run the scope "
                "commands; new assignments can take up to 2 hours",
            )
        else:
            # Only a 403 on a mailbox outside the scope proves the Exchange scoping works.
            outside = _mail_status(client, ctx.user.email, "/mailFolders/inbox")
            if ctx.user.email.lower() == s.mail_mailbox.lower():
                # the admin signed in as the support mailbox: the probe cannot show the scope
                mail = _step("mail", "ok", f"Mail works for {s.mail_mailbox} (scope not checked)")
            elif outside == 403:
                mail = _step("mail", "ok", f"Mail works for {s.mail_mailbox} and only that mailbox")
            elif outside == 200:
                mail = _step(
                    "mail",
                    "error",
                    "The mail app can read mailboxes outside its scope: run the scope commands",
                )
            else:
                mail = _step(
                    "mail",
                    "error",
                    f"Could not check the mailbox scope (HTTP {outside}), try again in a minute",
                )
        # The first technician (members of PSA Techs take appointments), else the mailbox.
        tech = ctx.db.execute(
            select(User.email).where(User.role == "tech", User.is_active).order_by(User.id)
        ).scalar()
        who = tech or s.mail_mailbox
        cal = _mail_status(client, who, "/calendar")
        calendar = (
            _step("calendar", "ok", f"Calendar works for {who}")
            if cal == 200
            else _step(
                "calendar",
                "error",
                f"The mail app cannot read the calendar of {who} (HTTP {cal}): "
                "run the calendar scope commands",
            )
        )
    except GraphError as exc:  # sign-in or network failure: public message only
        mail = _step("mail", "error", exc.public)
        calendar = _step("calendar", "error", exc.public)
    finally:
        http.close()
    return [mail, calendar]


def verify(ctx: Ctx) -> list[dict]:
    s = get_settings()
    staff = (
        _step("staff_sso", "ok", "Staff sign-in with Microsoft works")
        if s.entra_configured
        else _step("staff_sso", "missing", "Staff sign-in with Microsoft is not configured")
    )
    vault = KeyVault.from_settings()  # one instance: it caches the managed identity token
    return [staff, _check_portal(ctx, vault), *_check_mail_and_calendar(ctx, vault)]


def finish(ctx: Ctx) -> list[str]:
    """Remove the three admin scopes from the staff app's delegated grants (deleting a grant
    that has nothing else left), then discard the token. Returns the scopes removed."""
    token = onboarding_auth.get_admin_token(ctx)
    staff_sp = _service_principal(token, get_settings().entra_client_id)
    removed: set[str] = set()
    if staff_sp:
        grants = _graph(
            token, "GET", f"/oauth2PermissionGrants?$filter=clientId eq '{_odata(staff_sp['id'])}'"
        ).get("value", [])
        for grant in grants:
            scopes = (grant.get("scope") or "").split()
            keep = [x for x in scopes if x not in ADMIN_SCOPE_NAMES]
            if len(keep) == len(scopes):
                continue
            removed.update(x for x in scopes if x in ADMIN_SCOPE_NAMES)
            path = f"/oauth2PermissionGrants/{quote(grant['id'], safe='')}"
            if keep:
                _graph(token, "PATCH", path, json={"scope": " ".join(keep)})
            else:
                _graph(token, "DELETE", path)
    onboarding_auth.discard(ctx)
    audit.record(ctx.db, ctx.user, "onboarding.finished", detail={"removed": sorted(removed)})
    return sorted(removed)
