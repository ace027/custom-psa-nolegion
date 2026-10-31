"""Portal "Sign in with Microsoft": a multi-tenant app whose tokens map to existing portal contacts
of the organization that owns the token's tenant. The IdP is faked; authlib's own checks
(signature, aud, exp, nonce) are not under test here, our issuer and mapping rules are."""

import pytest
from authlib.jose import JWTClaims
from authlib.jose.errors import InvalidClaimError
from sqlalchemy import text

from app.auth import oidc
from app.config import get_settings
from tests.test_portal import (  # noqa: F401
    add_contact,
    anon_client,
    link_emails,
    portal_on,
    sign_in,
    two_clients,
)

TID_A = "aaaaaaaa-1111-2222-3333-444444444444"
TID_B = "bbbbbbbb-1111-2222-3333-444444444444"
DENIED = "/portal?sso=denied"


class FakePortalEntra:
    def __init__(self, claims=None, boom=False):
        self.claims, self.boom, self.calls = claims, boom, []

    async def authorize_access_token(self, request, **kwargs):
        self.calls.append(kwargs)
        if self.boom:
            raise RuntimeError("bad state")
        return {"userinfo": self.claims}

    async def authorize_redirect(self, request, redirect_uri):
        from starlette.responses import RedirectResponse

        assert redirect_uri.endswith("/api/v1/portal/sso/callback")
        return RedirectResponse("https://login.microsoftonline.com/organizations/x", 302)


class FakeOAuth:
    def __init__(self, portal):
        self.entra_portal = portal


@pytest.fixture
def sso_configured(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "portal_entra_client_id", "portal-client")
    monkeypatch.setattr(s, "portal_entra_client_secret", "portal-secret")


@pytest.fixture
def idp(monkeypatch, sso_configured):
    """Point the callback at a fake IdP that will return the given claims."""

    def _use(claims=None, boom=False):
        fake = FakePortalEntra(claims, boom)
        monkeypatch.setattr(oidc, "get_oauth", lambda: FakeOAuth(fake))
        return fake

    return _use


@pytest.fixture
def tenants(admin, two_clients):
    a, b = two_clients
    assert admin.patch(f"/api/v1/organizations/{a}", json={"entra_tenant_id": TID_A}).is_success
    assert admin.patch(f"/api/v1/organizations/{b}", json={"entra_tenant_id": TID_B}).is_success
    return a, b


def claims(tid=TID_A, oid="oid-pat", email="Pat@Acme.com", **extra):
    out = {"tid": tid, "oid": oid, "email": email, **extra}
    return {k: v for k, v in out.items() if v is not None}


def callback(client=None):
    c = client or anon_client()
    return c, c.get("/api/v1/portal/sso/callback", follow_redirects=False)


def failures(admin):
    items = admin.get("/api/v1/audit", params={"action": "portal.login", "limit": 200}).json()
    return [e for e in items["items"] if e["action"] == "portal.login_failed"]


def oid_of(owner, contact_id):
    return owner.execute(
        text("SELECT entra_oid FROM contacts WHERE id = :i"), {"i": contact_id}
    ).scalar_one()


# ---- success ----
def test_sso_success_binds_oid_sets_cookie_and_audits(admin, owner, portal_on, tenants, idp):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    fake = idp(claims())
    c, r = callback()
    assert r.status_code == 303 and r.headers["location"].endswith("/portal")
    assert "psa_portal" in r.cookies and "psa_session" not in r.cookies
    assert fake.calls == [{"claims_options": oidc.PORTAL_CLAIMS_OPTIONS}]
    assert c.get("/api/v1/portal/me").json()["email"] == pat["email"]
    assert oid_of(owner, pat["id"]) == "oid-pat"
    logins = admin.get("/api/v1/audit", params={"action": "portal.login"}).json()["items"]
    ok = [e for e in logins if e["action"] == "portal.login"]
    assert ok[0]["detail"] == {"contact_id": pat["id"], "method": "sso"}
    contact = admin.get(f"/api/v1/organizations/{a}/contacts").json()[0]
    assert contact["entra_linked"] is True and "entra_oid" not in contact


def test_second_login_matches_by_oid_after_email_changes(admin, portal_on, tenants, idp):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    idp(claims())
    assert callback()[1].headers["location"].endswith("/portal")
    idp(claims(email="patricia.new@acme.com"))
    c, r = callback()
    assert r.headers["location"].endswith("/portal")
    assert c.get("/api/v1/portal/me").json()["email"] == pat["email"]


def test_preferred_username_is_used_when_email_claim_is_absent(admin, portal_on, tenants, idp):
    a, _ = tenants
    add_contact(admin, a, "Pat", "pat@acme.com")
    idp(claims(email=None, preferred_username="PAT@acme.com"))
    assert callback()[1].headers["location"].endswith("/portal")


def test_tenant_id_match_is_case_insensitive(admin, portal_on, tenants, idp):
    a, _ = tenants
    add_contact(admin, a, "Pat", "pat@acme.com")
    idp(claims(tid=TID_A.upper()))
    assert callback()[1].headers["location"].endswith("/portal")


def test_one_time_link_still_works_after_binding_and_gives_same_contact(
    admin, tenants, idp, sign_in
):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    idp(claims())
    sso_client, r = callback()
    assert r.headers["location"].endswith("/portal")
    link_client = sign_in("pat@acme.com")
    sso_me = sso_client.get("/api/v1/portal/me").json()
    link_me = link_client.get("/api/v1/portal/me").json()
    assert sso_me == link_me and link_me["email"] == pat["email"]


# ---- denials: every one audited with a reason, same redirect, no cookie, no binding ----
def _assert_denied(admin, owner, reason, contact_id=None, expected_oid=None):
    c, r = callback()
    assert r.status_code == 303 and r.headers["location"].endswith(DENIED)
    assert "psa_portal" not in r.cookies
    assert c.get("/api/v1/portal/me").status_code == 401
    failed = failures(admin)
    assert failed[0]["detail"] == {"reason": reason, "method": "sso"}
    assert failed[0]["actor_type"] == "anonymous"
    if contact_id is not None:
        assert oid_of(owner, contact_id) == expected_oid


@pytest.mark.parametrize(
    "token_claims,reason",
    [
        (claims(tid="cccccccc-1111-2222-3333-444444444444"), "unknown_tenant"),
        (claims(tid=None), "missing_tid"),
        (claims(oid=None), "missing_oid"),
        (claims(email=None), "missing_email"),
        (claims(email="stranger@acme.com"), "no_contact"),
    ],
)
def test_claims_denied(admin, owner, portal_on, tenants, idp, token_claims, reason):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    idp(token_claims)
    _assert_denied(admin, owner, reason, pat["id"])


def test_email_of_a_contact_in_another_org_is_denied(admin, owner, portal_on, tenants, idp):
    """Tenant A's admins control the email claim, so it is only trusted inside organization A."""
    _, b = tenants
    other = add_contact(admin, b, "Bea", "bea@beta.com")
    idp(claims(tid=TID_A, email="bea@beta.com"))
    _assert_denied(admin, owner, "no_contact", other["id"])


def test_oid_bound_in_another_org_is_denied(admin, owner, portal_on, tenants, idp):
    a, b = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    bea = add_contact(admin, b, "Bea", "bea@beta.com")
    owner.execute(text("UPDATE contacts SET entra_oid = 'oid-pat' WHERE id = :i"), {"i": bea["id"]})
    idp(claims())
    _assert_denied(admin, owner, "oid_bound_elsewhere", pat["id"])


def test_portal_access_off_is_denied(admin, owner, portal_on, tenants, idp):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com", portal=False)
    idp(claims())
    _assert_denied(admin, owner, "no_portal_access", pat["id"])


def test_portal_access_off_is_denied_even_when_matched_by_oid(
    admin, owner, portal_on, tenants, idp
):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    idp(claims())
    callback()
    admin.patch(f"/api/v1/contacts/{pat['id']}", json={"portal_access": False})
    _assert_denied(admin, owner, "no_portal_access", pat["id"], "oid-pat")


def test_archived_contact_is_denied(admin, owner, portal_on, tenants, idp):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    admin.post(f"/api/v1/contacts/{pat['id']}/archive")
    idp(claims())
    _assert_denied(admin, owner, "contact_archived", pat["id"])


def test_archived_contact_is_denied_when_matched_by_oid(admin, owner, portal_on, tenants, idp):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    idp(claims())
    callback()
    admin.post(f"/api/v1/contacts/{pat['id']}/archive")
    _assert_denied(admin, owner, "contact_archived", pat["id"], "oid-pat")


def test_archived_org_is_denied(admin, owner, portal_on, tenants, idp):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    admin.post(f"/api/v1/organizations/{a}/archive")
    idp(claims())
    _assert_denied(admin, owner, "organization_archived", pat["id"])


def test_contact_already_bound_to_a_different_oid_is_denied(admin, owner, portal_on, tenants, idp):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    owner.execute(
        text("UPDATE contacts SET entra_oid = 'someone-else' WHERE id = :i"), {"i": pat["id"]}
    )
    idp(claims())
    _assert_denied(admin, owner, "oid_mismatch", pat["id"], "someone-else")


def test_portal_disabled_is_denied(admin, owner, tenants, idp):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    fake = idp(claims())
    _assert_denied(admin, owner, "portal_disabled", pat["id"])
    assert fake.calls == []  # refused before any token exchange


def test_token_exchange_failure_is_denied(admin, owner, portal_on, tenants, idp):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    idp(boom=True)
    _assert_denied(admin, owner, "token_exchange", pat["id"])


def test_callback_when_sso_not_configured_is_denied(admin, owner, portal_on, monkeypatch):
    monkeypatch.setattr(get_settings(), "portal_entra_client_id", "")
    _assert_denied(admin, owner, "not_configured")


def test_unlinked_contact_rebinds_on_next_sign_in(admin, owner, portal_on, tenants, idp):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    idp(claims())
    sso_client, _ = callback()
    r = admin.patch(f"/api/v1/contacts/{pat['id']}", json={"unlink_entra": True})
    assert r.status_code == 200 and r.json()["entra_linked"] is False
    assert oid_of(owner, pat["id"]) is None
    assert sso_client.get("/api/v1/portal/me").status_code == 401  # sessions ended
    audit = admin.get("/api/v1/audit", params={"action": "contact.update"}).json()["items"]
    assert audit[0]["before"]["entra_oid"] == "oid-pat" and audit[0]["after"]["entra_oid"] is None
    idp(claims(oid="oid-new"))
    assert callback()[1].headers["location"].endswith("/portal")
    assert oid_of(owner, pat["id"]) == "oid-new"


# ---- the issuer check for the multi-tenant app ----
def test_issuer_must_belong_to_the_tokens_own_tenant():
    good = f"https://login.microsoftonline.com/{TID_A}/v2.0"
    assert oidc.portal_issuer_matches_tid({"tid": TID_A}, good)
    assert not oidc.portal_issuer_matches_tid({"tid": TID_B}, good)
    assert not oidc.portal_issuer_matches_tid({}, good)
    assert not oidc.portal_issuer_matches_tid({"tid": TID_A}, None)
    assert not oidc.portal_issuer_matches_tid(
        {"tid": TID_A}, "https://login.microsoftonline.com/{tenantid}/v2.0"
    )


def test_issuer_validator_is_enforced_by_authlib_claims():
    ok = JWTClaims(
        {"iss": f"https://login.microsoftonline.com/{TID_A}/v2.0", "tid": TID_A},
        {},
        oidc.PORTAL_CLAIMS_OPTIONS,
    )
    ok.validate()
    for payload in (
        {"iss": f"https://login.microsoftonline.com/{TID_B}/v2.0", "tid": TID_A},
        {"iss": "https://evil.example/v2.0", "tid": TID_A},
    ):
        with pytest.raises(InvalidClaimError):
            JWTClaims(payload, {}, oidc.PORTAL_CLAIMS_OPTIONS).validate()


def test_portal_client_is_registered_only_when_configured(monkeypatch):
    s = get_settings()
    oidc.get_oauth.cache_clear()
    try:
        monkeypatch.setattr(s, "portal_entra_client_id", "")
        assert "entra_portal" not in oidc.get_oauth()._clients
        oidc.get_oauth.cache_clear()
        monkeypatch.setattr(s, "portal_entra_client_id", "portal-client")
        monkeypatch.setattr(s, "portal_entra_client_secret", "portal-secret")
        client = oidc.get_oauth().create_client("entra_portal")
        assert client._server_metadata_url == (
            "https://login.microsoftonline.com/organizations/v2.0/.well-known/openid-configuration"
        )
        assert client.client_kwargs["code_challenge_method"] == "S256"
    finally:
        oidc.get_oauth.cache_clear()


# ---- login options and the login redirect ----
def test_login_options_and_login_route(admin, monkeypatch, idp):
    anon = anon_client()
    assert anon.get("/api/v1/portal/login-options").json() == {"sso": False}  # portal off
    assert anon.get("/api/v1/portal/sso/login", follow_redirects=False).status_code == 404
    admin.patch("/api/v1/settings", json={"portal_enabled": True})
    idp(claims())
    assert anon.get("/api/v1/portal/login-options").json() == {"sso": True}
    r = anon.get("/api/v1/portal/sso/login", follow_redirects=False)
    assert r.status_code == 302 and "login.microsoftonline.com" in r.headers["location"]
    monkeypatch.setattr(get_settings(), "portal_entra_client_secret", "")
    assert anon.get("/api/v1/portal/login-options").json() == {"sso": False}
    assert anon.get("/api/v1/portal/sso/login", follow_redirects=False).status_code == 404
