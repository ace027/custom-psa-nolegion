import base64
import json

import httpx
import pytest

from app import worker
from app.config import get_settings
from app.mail.graph import GraphClient, GraphError, parse_message

RAW = {
    "id": "AAA",
    "internetMessageId": "<abc@x>",
    "conversationId": "c1",
    "subject": "Hello",
    "from": {"emailAddress": {"address": "Pat@Acme.com", "name": "Pat"}},
    "toRecipients": [{"emailAddress": {"address": "support@msp.com"}}],
    "body": {"contentType": "text", "content": "Hi there"},
    "receivedDateTime": "2026-09-30T12:00:00Z",
    "hasAttachments": True,
    "internetMessageHeaders": [
        {"name": "Auto-Submitted", "value": "no"},
        {"name": "In-Reply-To", "value": "<p@x>"},
    ],
}


def make_client(handler):
    calls = []

    def wrapped(request: httpx.Request):
        calls.append(request)
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(wrapped))
    return GraphClient("tenant", "cid", "secret", "support@msp.com", http=http), calls


def token_ok(request):
    return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})


def router(**routes):
    def handler(request: httpx.Request):
        if request.url.host == "login.microsoftonline.com":
            return token_ok(request)
        for key, fn in routes.items():
            if key == f"{request.method} {request.url.path.split('/users/support@msp.com')[-1]}":
                return fn(request)
        return httpx.Response(404, json={"error": "unrouted " + request.url.path})

    return handler


def test_parse_message_normalises_fields():
    m = parse_message(RAW)
    assert m.from_email == "pat@acme.com" and m.to_emails == ["support@msp.com"]
    assert m.headers == {"auto-submitted": "no", "in-reply-to": "<p@x>"}
    assert m.body_text == "Hi there" and m.received_at.year == 2026 and m.has_attachments
    bare = parse_message({"id": "B", "sender": {"emailAddress": {"address": "S@x.com"}}})
    assert bare.from_email == "s@x.com" and bare.subject == "" and bare.received_at is None


def test_list_unread_asks_for_text_bodies_unread_only_and_sorts_oldest_first():
    newer = {**RAW, "id": "NEW", "receivedDateTime": "2026-09-30T13:00:00Z"}

    def listing(request):
        assert request.headers["Authorization"] == "Bearer tok"
        assert request.headers["Prefer"] == 'outlook.body-content-type="text"'
        assert request.url.params["$filter"] == "isRead eq false"
        assert "$orderby" not in request.url.params  # Graph rejects filter+orderby mismatches
        assert "internetMessageHeaders" in request.url.params["$select"]
        return httpx.Response(200, json={"value": [newer, RAW]})

    client, _ = make_client(router(**{"GET /mailFolders/inbox/messages": listing}))
    assert [m.id for m in client.list_unread()] == ["AAA", "NEW"]


def test_token_is_cached_between_calls():
    client, calls = make_client(
        router(
            **{"GET /mailFolders/inbox/messages": lambda r: httpx.Response(200, json={"value": []})}
        )
    )
    client.list_unread()
    client.list_unread()
    assert sum(1 for c in calls if c.url.host == "login.microsoftonline.com") == 1
    body = dict(
        x.split("=")
        for x in next(c for c in calls if c.url.host == "login.microsoftonline.com")
        .content.decode()
        .split("&")
    )
    assert body["grant_type"] == "client_credentials" and "graph.microsoft.com" in body["scope"]


def test_token_failure_raises_graph_error():
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, text="bad")))
    with pytest.raises(GraphError, match="token request failed"):
        GraphClient("t", "c", "s", "m@x.com", http=http).list_unread()


def test_api_errors_become_graph_errors():
    client, _ = make_client(
        router(
            **{
                "GET /mailFolders/inbox/messages": lambda r: httpx.Response(
                    403, text="Access denied"
                )
            }
        )
    )
    with pytest.raises(GraphError, match="403"):
        client.list_unread()


def test_attachments_inline_fallback_and_filters():
    files = [
        {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "id": "1",
            "name": "a.txt",
            "contentType": "text/plain",
            "size": 3,
            "contentBytes": base64.b64encode(b"abc").decode(),
        },
        {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "id": "2",
            "name": "big.bin",
            "size": 4,
            "contentType": "x/y",
        },  # no inline bytes -> fetched from $value
        {
            "@odata.type": "#microsoft.graph.fileAttachment",
            "id": "3",
            "name": "huge.bin",
            "size": 999,
        },
        {"@odata.type": "#microsoft.graph.itemAttachment", "id": "4", "name": "fwd.eml", "size": 1},
    ]
    client, calls = make_client(
        router(
            **{
                "GET /messages/AAA/attachments": lambda r: httpx.Response(
                    200, json={"value": files}
                ),
                "GET /messages/AAA/attachments/2/$value": lambda r: httpx.Response(
                    200, content=b"DATA"
                ),
            }
        )
    )
    got = client.get_attachments("AAA", max_bytes=100)
    assert [(a.name, a.content) for a in got] == [("a.txt", b"abc"), ("big.bin", b"DATA")]
    assert not any("/3" in str(c.url) or "/4" in str(c.url) for c in calls)


def test_mark_read_and_send_mail_payloads():
    seen = {}

    def patch(request):
        seen["patch"] = json.loads(request.content)
        return httpx.Response(200, json={})

    def send(request):
        seen["send"] = json.loads(request.content)
        return httpx.Response(202)

    client, _ = make_client(router(**{"PATCH /messages/AAA": patch, "POST /sendMail": send}))
    client.mark_read("AAA")
    client.send_mail(["pat@acme.com"], "[#10001] Hi", "Body text")
    assert seen["patch"] == {"isRead": True}
    msg = seen["send"]["message"]
    assert msg["subject"] == "[#10001] Hi" and msg["body"] == {
        "contentType": "Text",
        "content": "Body text",
    }
    assert msg["toRecipients"] == [{"emailAddress": {"address": "pat@acme.com"}}]
    assert seen["send"]["saveToSentItems"] is True


# ---- worker entrypoint ----
def test_worker_idles_and_exits_once_when_mail_is_not_configured(monkeypatch):
    monkeypatch.setattr(get_settings(), "graph_tenant_id", "")
    assert not get_settings().mail_configured
    assert worker.main(["--once"]) == 0


def test_worker_runs_a_single_cycle_when_configured(monkeypatch):
    s = get_settings()
    for k, v in (
        ("graph_tenant_id", "t"),
        ("graph_client_id", "c"),
        ("graph_client_secret", "s"),
        ("mail_mailbox", "support@msp.com"),
    ):
        monkeypatch.setattr(s, k, v)
    cycles = []
    monkeypatch.setattr(worker, "run_cycle", lambda client, mailbox: cycles.append(mailbox))
    assert worker.main(["--once"]) == 0
    assert cycles == ["support@msp.com"]
    assert isinstance(worker.build_client(), GraphClient)


def test_sovereign_cloud_urls_are_used_for_token_and_api_calls():
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        if "oauth2" in request.url.path:
            assert request.content.decode().count("graph.microsoft.us%2F.default") == 1 or (
                "graph.microsoft.us" in request.content.decode()
            )
            return httpx.Response(200, json={"access_token": "t", "expires_in": 3600})
        return httpx.Response(200, json={"value": []})

    client = GraphClient(
        "tid",
        "cid",
        "sec",
        "support@msp.com",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        base_url="https://graph.microsoft.us/v1.0",
        login_url="https://login.microsoftonline.us",
    )
    client.list_unread()
    assert seen[0].url.host == "login.microsoftonline.us"
    assert seen[1].url.host == "graph.microsoft.us"
