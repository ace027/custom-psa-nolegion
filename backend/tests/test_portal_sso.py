"""Portal "Sign in with Microsoft": a multi-tenant app whose tokens map to existing portal contacts
of the organization that owns the token's tenant. The IdP is faked; authlib's own checks
(signature, exp, nonce) are not under test here; our issuer/audience options and mapping rules are.
A first sign-in matched only by email is confirmed through an emailed one-time link."""

import hashlib

import pytest
from authlib.jose import JWTClaims
from authlib.jose.errors import InvalidClaimError, MissingClaimError
from sqlalchemy import text

from app.auth import oidc
from app.config import get_settings
from tests.test_portal import (  # noqa: F401
    add_contact,
    anon_client,
    link_emails,
    portal_on,
    sign_in,
    token_for,
    two_clients,
)

TID_A = "aaaaaaaa-1111-2222-3333-444444444444"
TID_B = "bbbbbbbb-1111-2222-3333-444444444444"
DENIED = "/portal?sso=denied"
CONFIRM = "/portal?sso=confirm"


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


def bind(owner, contact_id, oid="oid-pat"):
    owner.execute(
        text("UPDATE contacts SET entra_oid = :o WHERE id = :i"), {"o": oid, "i": contact_id}
    )


def events(admin, action):
    items = admin.get("/api/v1/audit", params={"action": action, "limit": 200}).json()["items"]
    return [e for e in items if e["action"] == action]


def verify(link_emails, email="pat@acme.com", client=None):
    """Redeem the latest link; pass the SSO client to redeem it in the same browser."""
    c = client or anon_client()
    return c, c.post("/api/v1/portal/verify", json={"token": token_for(link_emails, email)})


@pytest.fixture
def link_sso(mail_ready, link_emails):
    """Full first sign-in: SSO callback (email match) -> confirm email -> redeem the link."""

    def _link(idp_use, token_claims=None, email="pat@acme.com"):
        idp_use(token_claims or claims())
        browser, r = callback()
        assert r.headers["location"].endswith(CONFIRM)
        c, r = verify(link_emails, email, browser)
        assert r.status_code == 200, r.text
        return c

    return _link


# ---- first sign-in: an email match is confirmed through an emailed link ----
def test_first_sso_login_sends_a_confirm_link_and_binds_nothing(
    admin, owner, portal_on, mail_ready, link_emails, tenants, idp
):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    fake = idp(claims())
    c, r = callback()
    assert r.status_code == 303 and r.headers["location"].endswith(CONFIRM)
    assert "psa_portal" not in r.cookies
    confirm_cookie = r.headers["set-cookie"]
    assert confirm_cookie.startswith("psa_portal_sso_confirm=")
    assert "HttpOnly" in confirm_cookie and "Path=/api/v1/portal" in confirm_cookie
    assert "SameSite=lax" in confirm_cookie and "Max-Age=900" in confirm_cookie
    assert fake.calls == [{"claims_options": oidc.portal_claims_options()}]
    assert c.get("/api/v1/portal/me").status_code == 401
    assert oid_of(owner, pat["id"]) is None
    assert owner.execute(text("SELECT count(*) FROM portal_sessions")).scalar_one() == 0
    mail = link_emails("pat@acme.com")
    assert len(mail) == 1 and "confirm that the Microsoft account is yours" in mail[0].body_text
    assert "same browser you used to sign in with Microsoft" in mail[0].body_text
    pending = owner.execute(
        text(
            "SELECT bind_entra_oid, bind_entra_tenant_id, bind_browser_hash FROM portal_login_tokens"
        )
    ).one()
    secret = c.cookies["psa_portal_sso_confirm"]
    assert tuple(pending) == ("oid-pat", TID_A, hashlib.sha256(secret.encode()).hexdigest())
    requested = events(admin, "portal.sso_link_requested")
    assert requested[0]["detail"] == {"contact_id": pat["id"], "sent": True}
    assert events(admin, "portal.login") == []


def test_confirm_link_binds_the_oid_and_then_sso_signs_in_directly(
    admin, owner, portal_on, link_sso, tenants, idp
):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    c = link_sso(idp)
    assert c.get("/api/v1/portal/me").json()["email"] == pat["email"]
    assert oid_of(owner, pat["id"]) == "oid-pat"
    assert events(admin, "portal.sso_linked")[0]["detail"] == {"contact_id": pat["id"]}
    login = events(admin, "portal.login")[0]
    assert login["detail"] == {"contact_id": pat["id"], "method": "sso_confirm"}
    contact = admin.get(f"/api/v1/organizations/{a}/contacts").json()[0]
    assert contact["entra_linked"] is True and "entra_oid" not in contact

    idp(claims())
    c2, r = callback()
    assert r.status_code == 303 and r.headers["location"].endswith("/portal")
    assert "psa_portal" in r.cookies and "psa_session" not in r.cookies
    assert c2.get("/api/v1/portal/me").json()["email"] == pat["email"]
    assert events(admin, "portal.login")[0]["detail"] == {"contact_id": pat["id"], "method": "sso"}


def test_second_login_matches_by_oid_after_email_changes(admin, portal_on, link_sso, tenants, idp):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    link_sso(idp)
    idp(claims(email="patricia.new@acme.com"))
    c, r = callback()
    assert r.headers["location"].endswith("/portal")
    assert c.get("/api/v1/portal/me").json()["email"] == pat["email"]


def test_preferred_username_is_used_when_email_claim_is_absent(
    admin, owner, portal_on, link_sso, tenants, idp
):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    link_sso(idp, claims(email=None, preferred_username="PAT@acme.com"))
    assert oid_of(owner, pat["id"]) == "oid-pat"


def test_tenant_id_match_is_case_insensitive(admin, owner, portal_on, link_sso, tenants, idp):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    link_sso(idp, claims(tid=TID_A.upper()))
    assert oid_of(owner, pat["id"]) == "oid-pat"


def test_one_time_link_still_works_after_binding_and_gives_same_contact(
    admin, tenants, idp, sign_in, link_sso
):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    sso_client = link_sso(idp)
    link_client = sign_in("pat@acme.com")
    sso_me = sso_client.get("/api/v1/portal/me").json()
    link_me = link_client.get("/api/v1/portal/me").json()
    assert sso_me == link_me and link_me["email"] == pat["email"]


def test_plain_link_does_not_bind(admin, owner, tenants, sign_in):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    sign_in("pat@acme.com")
    assert oid_of(owner, pat["id"]) is None
    assert (
        events(admin, "portal.sso_linked") == [] and events(admin, "portal.sso_link_skipped") == []
    )


@pytest.mark.parametrize(
    "change", ["contact_already_linked", "oid_bound_elsewhere", "tenant_changed"]
)
def test_confirm_link_signs_in_without_binding_when_things_changed(
    admin, owner, portal_on, mail_ready, link_emails, tenants, idp, change
):
    a, b = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    bea = add_contact(admin, b, "Bea", "bea@beta.com")
    idp(claims())
    browser, r = callback()
    assert r.headers["location"].endswith(CONFIRM)
    expected_oid = None
    if change == "contact_already_linked":
        bind(owner, pat["id"], "oid-other")
        expected_oid = "oid-other"
    elif change == "oid_bound_elsewhere":
        bind(owner, bea["id"], "oid-pat")
    else:
        new_tid = "cccccccc-1111-2222-3333-444444444444"
        assert admin.patch(
            f"/api/v1/organizations/{a}", json={"entra_tenant_id": new_tid}
        ).is_success
    c, r = verify(link_emails, client=browser)
    assert r.status_code == 200  # the link still proves mailbox ownership
    assert c.get("/api/v1/portal/me").json()["email"] == pat["email"]
    assert oid_of(owner, pat["id"]) == expected_oid
    skipped = events(admin, "portal.sso_link_skipped")
    assert skipped[0]["detail"] == {"contact_id": pat["id"], "reason": change}
    assert events(admin, "portal.sso_linked") == []


def test_confirm_link_binds_only_in_the_browser_that_signed_in(
    admin, owner, portal_on, mail_ready, link_emails, tenants, idp
):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    idp(claims())
    browser, _ = callback()
    assert browser.cookies.get("psa_portal_sso_confirm")
    c, r = verify(link_emails, client=browser)
    assert r.status_code == 200 and oid_of(owner, pat["id"]) == "oid-pat"
    cleared = r.headers["set-cookie"]
    assert 'psa_portal_sso_confirm=""' in cleared and "Max-Age=0" in cleared
    assert "Path=/api/v1/portal" in cleared
    assert browser.cookies.get("psa_portal_sso_confirm") is None


@pytest.mark.parametrize("cookie", [None, "forged-value"])
def test_confirm_link_from_another_browser_signs_in_without_binding(
    admin, owner, portal_on, mail_ready, link_emails, tenants, idp, cookie
):
    """Account-linking CSRF: an attacker's Microsoft sign-in mails the victim, the victim clicks it
    in their own browser. They are signed in as themselves; the attacker's oid is NOT bound."""
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    idp(claims(oid="oid-attacker"))
    callback()
    victim = anon_client()
    if cookie:
        victim.cookies.set("psa_portal_sso_confirm", cookie, path="/api/v1/portal")
    c, r = verify(link_emails, client=victim)
    assert r.status_code == 200
    assert c.get("/api/v1/portal/me").json()["email"] == pat["email"]
    assert oid_of(owner, pat["id"]) is None
    skipped = events(admin, "portal.sso_link_skipped")
    assert skipped[0]["detail"] == {"contact_id": pat["id"], "reason": "different_browser"}
    assert events(admin, "portal.sso_linked") == []
    assert "psa_portal_sso_confirm=" in r.headers["set-cookie"]  # cleared either way
    idp(claims(oid="oid-attacker"))
    assert callback()[1].headers["location"].endswith(CONFIRM)  # attacker still not linked


def test_plain_link_does_not_touch_the_confirm_cookie(admin, tenants, sign_in):
    a, _ = tenants
    add_contact(admin, a, "Pat", "pat@acme.com")
    c = sign_in("pat@acme.com")
    assert c.cookies.get("psa_portal_sso_confirm") is None


def test_rate_limited_confirm_request_still_redirects_to_confirm(
    admin, owner, portal_on, mail_ready, link_emails, tenants, idp
):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    anon = anon_client()
    for _ in range(3):
        anon.post("/api/v1/portal/login-link", json={"email": "pat@acme.com"})
    assert len(link_emails()) == 3
    idp(claims())
    c, r = callback()
    assert r.status_code == 303 and r.headers["location"].endswith(CONFIRM)
    assert "set-cookie" not in r.headers  # no token issued, so no confirm cookie
    assert len(link_emails()) == 3
    assert events(admin, "portal.sso_link_rate_limited")[0]["detail"] == {"contact_id": pat["id"]}
    assert events(admin, "portal.sso_link_requested") == []
    assert oid_of(owner, pat["id"]) is None


def test_confirm_request_without_mail_still_redirects_to_confirm(
    admin, owner, portal_on, link_emails, tenants, idp
):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    idp(claims())
    _, r = callback()
    assert r.headers["location"].endswith(CONFIRM) and "set-cookie" not in r.headers
    assert link_emails() == [] and oid_of(owner, pat["id"]) is None
    detail = events(admin, "portal.sso_link_requested")[0]["detail"]
    assert detail == {"contact_id": pat["id"], "sent": False, "reason": "mail_not_configured"}


def test_concurrent_oid_bind_is_denied_not_a_500(
    admin, owner, portal_on, mail_ready, link_emails, tenants, idp, monkeypatch
):
    """The holder check and the write race; the unique index decides and the loser is denied."""
    a, b = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    bea = add_contact(admin, b, "Bea", "bea@beta.com")
    idp(claims())
    browser, _ = callback()
    bind(owner, bea["id"], "oid-pat")
    monkeypatch.setattr(oidc, "_oid_holder", lambda db, oid: None)  # lose the race
    c, r = verify(link_emails, client=browser)
    assert r.status_code == 401 and "psa_portal" not in r.cookies
    assert c.get("/api/v1/portal/me").status_code == 401
    assert failures(admin)[0]["detail"] == {"reason": "oid_conflict", "method": "sso_confirm"}
    assert oid_of(owner, pat["id"]) is None


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
    bind(owner, pat["id"])
    admin.patch(f"/api/v1/contacts/{pat['id']}", json={"portal_access": False})
    idp(claims())
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
    bind(owner, pat["id"])
    admin.post(f"/api/v1/contacts/{pat['id']}/archive")
    idp(claims())
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
    bind(owner, pat["id"], "someone-else")
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


def test_unlinked_contact_rebinds_on_next_sign_in(
    admin, owner, portal_on, link_sso, link_emails, tenants, idp
):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    sso_client = link_sso(idp)
    r = admin.patch(f"/api/v1/contacts/{pat['id']}", json={"unlink_entra": True})
    assert r.status_code == 200 and r.json()["entra_linked"] is False
    assert oid_of(owner, pat["id"]) is None
    assert sso_client.get("/api/v1/portal/me").status_code == 401  # sessions ended
    audit = admin.get("/api/v1/audit", params={"action": "contact.update"}).json()["items"]
    assert audit[0]["before"]["entra_oid"] == "oid-pat" and audit[0]["after"]["entra_oid"] is None
    link_sso(idp, claims(oid="oid-new"))  # re-binding is confirmed by email again
    assert oid_of(owner, pat["id"]) == "oid-new"


# ---- changing a client's tenant id ends trust in oids bound under the old one ----
@pytest.mark.parametrize("new_tid", ["cccccccc-1111-2222-3333-444444444444", None])
def test_tenant_change_unlinks_contacts_and_ends_their_sessions(
    admin, owner, portal_on, tenants, idp, new_tid
):
    a, b = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    sam = add_contact(admin, a, "Sam", "sam@acme.com")
    bea = add_contact(admin, b, "Bea", "bea@beta.com")
    bind(owner, pat["id"])
    bind(owner, bea["id"], "oid-bea")
    idp(claims())
    sso_client, r = callback()
    assert r.headers["location"].endswith("/portal")
    r = admin.patch(f"/api/v1/organizations/{a}", json={"entra_tenant_id": new_tid})
    assert r.status_code == 200
    assert oid_of(owner, pat["id"]) is None and oid_of(owner, sam["id"]) is None
    assert oid_of(owner, bea["id"]) == "oid-bea"  # other clients untouched
    assert sso_client.get("/api/v1/portal/me").status_code == 401
    changed = events(admin, "organization.entra_tenant_changed")  # newest first
    assert changed[0]["detail"] == {"contacts_unlinked": 1}
    assert changed[0]["organization_id"] == a


def test_setting_the_same_tenant_id_again_is_a_no_op(admin, owner, portal_on, tenants, idp):
    a, _ = tenants
    pat = add_contact(admin, a, "Pat", "pat@acme.com")
    bind(owner, pat["id"])
    idp(claims())
    sso_client, _ = callback()
    before = len(events(admin, "organization.entra_tenant_changed"))  # the fixture's first set
    for same in (TID_A, TID_A.upper()):
        assert admin.patch(f"/api/v1/organizations/{a}", json={"entra_tenant_id": same}).is_success
    assert admin.patch(f"/api/v1/organizations/{a}", json={"name": "Acme Renamed"}).is_success
    assert oid_of(owner, pat["id"]) == "oid-pat"
    assert sso_client.get("/api/v1/portal/me").status_code == 200
    assert len(events(admin, "organization.entra_tenant_changed")) == before


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


def test_issuer_validator_is_enforced_by_authlib_claims(sso_configured):
    good_iss = f"https://login.microsoftonline.com/{TID_A}/v2.0"
    ok = JWTClaims(
        {"iss": good_iss, "tid": TID_A, "aud": "portal-client"}, {}, oidc.portal_claims_options()
    )
    ok.validate()
    for payload in (
        {"iss": f"https://login.microsoftonline.com/{TID_B}/v2.0", "tid": TID_A},
        {"iss": "https://evil.example/v2.0", "tid": TID_A},
    ):
        with pytest.raises(InvalidClaimError):
            JWTClaims(
                {**payload, "aud": "portal-client"}, {}, oidc.portal_claims_options()
            ).validate()


def test_audience_must_be_the_portal_app(sso_configured):
    """Passing claims_options replaces authlib's defaults, so aud is pinned explicitly."""
    base = {"iss": f"https://login.microsoftonline.com/{TID_A}/v2.0", "tid": TID_A}
    with pytest.raises(InvalidClaimError):
        JWTClaims({**base, "aud": "staff-client"}, {}, oidc.portal_claims_options()).validate()
    with pytest.raises(MissingClaimError):
        JWTClaims(base, {}, oidc.portal_claims_options()).validate()
    JWTClaims({**base, "aud": ["portal-client"]}, {}, oidc.portal_claims_options()).validate()


def test_portal_client_is_registered_only_when_configured(monkeypatch):
    s = get_settings()
    oidc.get_oauth.cache_clear()
    try:
        monkeypatch.setattr(s, "portal_entra_client_id", "")
        assert set(oidc.get_oauth()._clients) == {"entra_staff"}
        oidc.get_oauth.cache_clear()
        monkeypatch.setattr(s, "portal_entra_client_id", "portal-client")
        monkeypatch.setattr(s, "portal_entra_client_secret", "portal-secret")
        # neither client name is a prefix of the other (shared OIDC state cookie)
        assert set(oidc.get_oauth()._clients) == {"entra_staff", "entra_portal"}
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
