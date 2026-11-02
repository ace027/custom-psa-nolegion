"""Hudu articles on tickets: the client search and GET /tickets/{id}/hudu-articles."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import HTTPException

from app import hudu_articles
from app.db import new_session, set_org_scope
from app.deps import Ctx
from app.integrations.base import RemoteArticle
from app.integrations.hudu import HuduClient
from app.models import User
from app.routers import tickets as tickets_router
from app.scope import Scope
from tests.vendorfakes import HUDU, vendors  # noqa: F401


@pytest.fixture(autouse=True)
def empty_cache():
    hudu_articles._cache.clear()  # ticket ids restart in every test
    yield
    hudu_articles._cache.clear()


# ---- the client, against a fake Hudu ----
def article(id, company_id, updated, url=None, name=None):
    return {
        "id": id,
        "name": name or f"Article {id}",
        "company_id": company_id,
        "url": url or f"https://hudu.test/kb/{id}",
        "updated_at": updated,
        "content": "<p>secret runbook</p>",
    }


def test_search_merges_company_and_global_newest_first_with_relative_urls():
    seen = []

    def handler(req: httpx.Request):
        assert req.headers["x-api-key"] == "key" and req.url.path == "/api/v1/articles"
        params = dict(req.url.params)
        seen.append(params)
        if params.get("company_id") == "3":
            items = [
                article(1, 3, "2026-01-01T00:00:00Z", url="/kb/printer-1"),
                article(2, 3, "2026-03-01T00:00:00.000-05:00"),
                article(9, 4, "2026-05-01T00:00:00Z"),  # another company: never shown
            ]
        else:  # unfiltered: everything matching; only company_id null is global
            items = [
                article(2, 3, "2026-03-01T00:00:00Z"),
                article(5, None, "2026-02-01T00:00:00Z", url="kb/global-5"),
                article(6, None, None, url="javascript:alert(1)"),
                article(7, 4, "2026-06-01T00:00:00Z"),
            ]
        return httpx.Response(200, json={"articles": items})

    c = HuduClient("https://hudu.test/", "key", {}, httpx.MockTransport(handler))
    found = c.search_articles("printer offline", "3")
    assert [(a.id, a.scope) for a in found] == [("2", "client"), ("5", "global"), ("1", "client")]
    assert found[1].url == "https://hudu.test/kb/global-5"
    assert found[2].url == "https://hudu.test/kb/printer-1"
    assert found[2].title == "Article 1"
    assert found[2].updated_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert not hasattr(found[0], "content")
    assert [p.get("company_id") for p in seen] == ["3", None]
    assert all(p["search"] == "printer offline" for p in seen)
    assert c.search_articles("printer", "3", limit=1)[0].id == "2"


def test_search_without_a_company_returns_global_only():
    def handler(req: httpx.Request):
        assert "company_id" not in req.url.params
        items = [article(1, 3, "2026-01-01"), article(5, None, "2026-02-01")]
        return httpx.Response(200, json={"articles": items})

    c = HuduClient("https://hudu.test", "key", {}, httpx.MockTransport(handler))
    assert [(a.id, a.scope) for a in c.search_articles("vpn", None)] == [("5", "global")]


# ---- the route ----
def connect_hudu(admin, vendors, org_id=None):  # noqa: F811
    i = admin.post("/api/v1/integrations", json=HUDU).json()
    if org_id is not None:
        vendors[i["id"]].clients = {"33": "Acme"}
        (row,) = admin.post(f"/api/v1/integrations/{i['id']}/clients/refresh").json()
        r = admin.put(
            f"/api/v1/integrations/{i['id']}/clients/{row['id']}",
            json={"organization_id": org_id},
        )
        assert r.status_code == 200, r.text
    return vendors[i["id"]]


def remote(id, scope):
    return RemoteArticle(id, f"T{id}", f"https://hudu.example.com/kb/{id}", None, scope)


def test_not_configured(admin, make_ticket, vendors):  # noqa: F811
    t = make_ticket(subject="The printer is offline")
    r = admin.get(f"/api/v1/tickets/{t['id']}/hudu-articles")
    assert r.status_code == 200
    assert r.json() == {"configured": False, "articles": [], "error": None}
    assert admin.get("/api/v1/tickets/999999/hudu-articles").status_code == 404


def test_success_searches_mapped_company_and_caches(login, admin, org_ctx, make_ticket, vendors):  # noqa: F811
    fake = connect_hudu(admin, vendors, org_ctx["org"])
    fake.articles = [remote("1", "client"), remote("2", "global")]
    t = make_ticket(subject="Re: The printer is offline for my team")
    ro = login("read_only", "ro@example.com")
    r = ro.get(f"/api/v1/tickets/{t['id']}/hudu-articles")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["configured"] is True and body["error"] is None
    assert [(a["id"], a["scope"], a["title"]) for a in body["articles"]] == [
        ("1", "client", "T1"),
        ("2", "global", "T2"),
    ]
    assert fake.article_searches == [("printer offline team", "33")]
    assert ro.get(f"/api/v1/tickets/{t['id']}/hudu-articles").json() == body
    assert len(fake.article_searches) == 1  # cache hit: Hudu not called again


def test_hudu_error_is_200_with_message_and_not_cached(admin, make_ticket, vendors, caplog):  # noqa: F811
    fake = connect_hudu(admin, vendors)
    fake.fail_articles = True
    t = make_ticket(subject="VPN drops")
    for _ in range(2):
        r = admin.get(f"/api/v1/tickets/{t['id']}/hudu-articles")
        assert r.status_code == 200
        assert r.json() == {
            "configured": True,
            "articles": [],
            "error": "Hudu request failed: ReadTimeout",
        }
    assert fake.article_searches == [("VPN drops", None)] * 2
    assert "ReadTimeout" in caplog.text
    assert HUDU["credentials"]["api_key"] not in caplog.text + json.dumps(r.json())


def test_other_orgs_ticket_is_404_and_never_searched(admin, make_ticket, vendors):  # noqa: F811
    fake = connect_hudu(admin, vendors)
    t = make_ticket(subject="Printer down")
    with new_session() as db:
        scope = Scope.orgs(t["organization_id"] + 1000)
        set_org_scope(db, scope.rls_value())
        ctx = Ctx(db=db, user=db.get(User, admin.user["id"]), scope=scope)
        with pytest.raises(HTTPException) as e:
            tickets_router.ticket_hudu_articles(t["id"], ctx)
    assert e.value.status_code == 404
    assert fake.article_searches == []


def test_query_drops_stop_words_and_is_bounded():
    assert hudu_articles.query_for("Fwd: How do I reset my password?") == "reset password"
    assert len(hudu_articles.query_for("word " * 100)) <= 100
    assert hudu_articles.query_for("the a an") == ""
