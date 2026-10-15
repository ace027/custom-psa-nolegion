"""A tiny fake of the Microsoft Graph mail endpoints, for trying the mail worker locally
without a tenant. NOT for production. Stores state in memory.

    python dev/fake_graph.py                  # serves on http://localhost:9911
    GRAPH_BASE_URL=http://localhost:9911/v1.0 GRAPH_LOGIN_URL=http://localhost:9911 \
    GRAPH_TENANT_ID=t GRAPH_CLIENT_ID=c GRAPH_CLIENT_SECRET=s MAIL_MAILBOX=support@msp.example.com \
        python -m app.worker

Control endpoints (plain JSON):
    POST /_inject   {"from","subject","body","headers":{...}}   add an unread message to the inbox
    GET  /_sent                                                  messages the PSA sent out
    POST /_busy     {"user","start","end","status"}              inject a busy block
    GET  /_events                                                all stored calendar events
    POST /_fail     {"path_contains","status","count"}           next `count` matching requests fail

Calendar endpoints (under /v1.0/users/{user}):
    POST   /events                  create; idempotent on transactionId (same event returned, 201)
    PATCH  /events/{id}             merge; 404 if missing
    DELETE /events/{id}             204; 404 if missing
    POST   /calendar/getSchedule    busy items from stored events plus injected blocks
"""

import json
import os
import re
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

INBOX: list[dict] = []
SENT: list[dict] = []
EVENTS: dict[tuple[str, str], dict] = {}  # (user lowercased, event id) -> event
BUSY: list[dict] = []  # injected blocks: user, start, end, status
FAILS: list[dict] = []  # path_contains, status, count

_EVENTS_RE = re.compile(r"/users/([^/]+)/events(?:/([^/?]+))?$")
_SCHEDULE_RE = re.compile(r"/users/([^/]+)/calendar/getSchedule$")


def _dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S.0000000")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body=None):
        data = json.dumps(body if body is not None else {}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode() if n else ""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return dict(p.split("=", 1) for p in raw.split("&") if "=" in p)

    def log_message(self, *args):
        pass

    def _injected_failure(self) -> bool:
        if self.path.startswith("/_") or "/oauth2/" in self.path:
            return False
        for rule in FAILS:
            if rule["count"] > 0 and rule["path_contains"] in self.path:
                rule["count"] -= 1
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    self.rfile.read(n)
                self._send(rule["status"], {"error": "injected failure"})
                return True
        return False

    def _schedule(self, body: dict) -> dict:
        start, end = _dt(body["startTime"]["dateTime"]), _dt(body["endTime"]["dateTime"])
        out = []
        for sid in body.get("schedules", []):
            items = []
            blocks = [
                (e["start"]["dateTime"], e["end"]["dateTime"], e.get("showAs", "busy"))
                for (u, _), e in EVENTS.items()
                if u == sid.lower()
            ] + [
                (b["start"], b["end"], b["status"])
                for b in BUSY
                if b["user"].lower() == sid.lower()
            ]
            for bs, be, status in blocks:
                s_, e_ = _dt(bs), _dt(be)
                if s_ < end and e_ > start:
                    items.append(
                        {
                            "status": status,
                            "start": {"dateTime": _iso(s_), "timeZone": "UTC"},
                            "end": {"dateTime": _iso(e_), "timeZone": "UTC"},
                        }
                    )
            out.append({"scheduleId": sid, "scheduleItems": items})
        return {"value": out}

    def do_POST(self):
        if self._injected_failure():
            return
        body = self._body()
        if self.path == "/_busy":
            BUSY.append(body)
            return self._send(201, body)
        if self.path == "/_fail":
            FAILS.append(
                {
                    "path_contains": body["path_contains"],
                    "status": int(body["status"]),
                    "count": int(body.get("count", 1)),
                }
            )
            return self._send(201, {})
        m = _EVENTS_RE.search(self.path)
        if m and not m.group(2):
            user = m.group(1).lower()
            txn = body.get("transactionId")
            if txn:
                for (u, _), e in EVENTS.items():
                    if u == user and e.get("transactionId") == txn:
                        return self._send(201, e)
            eid = uuid.uuid4().hex
            EVENTS[(user, eid)] = event = {**body, "id": eid}
            return self._send(201, event)
        if _SCHEDULE_RE.search(self.path):
            return self._send(200, self._schedule(body))
        if self.path.endswith("/oauth2/v2.0/token"):
            return self._send(200, {"access_token": "fake", "expires_in": 3600})
        if self.path == "/_inject":
            mid = uuid.uuid4().hex
            INBOX.append(
                {
                    "id": mid,
                    "internetMessageId": f"<{mid}@fake.example>",
                    "conversationId": mid,
                    "subject": body.get("subject", ""),
                    "hasAttachments": False,
                    "isRead": False,
                    "from": {"emailAddress": {"address": body["from"]}},
                    "toRecipients": [],
                    "body": {"contentType": "text", "content": body.get("body", "")},
                    "receivedDateTime": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "internetMessageHeaders": [
                        {"name": k, "value": v} for k, v in (body.get("headers") or {}).items()
                    ],
                }
            )
            return self._send(201, {"id": mid})
        if self.path.endswith("/sendMail"):
            m = body["message"]
            SENT.append(
                {
                    "to": [r["emailAddress"]["address"] for r in m["toRecipients"]],
                    "subject": m["subject"],
                    "body": m["body"]["content"],
                }
            )
            return self._send(202)
        self._send(404, {"error": "unrouted"})

    def do_GET(self):
        if self._injected_failure():
            return
        if self.path == "/_events":
            return self._send(200, list(EVENTS.values()))
        if self.path == "/_sent":
            return self._send(200, SENT)
        if "/mailFolders/inbox/messages" in self.path:
            return self._send(200, {"value": [m for m in INBOX if not m["isRead"]]})
        if re.search(r"/messages/[^/]+/attachments", self.path):
            return self._send(200, {"value": []})
        self._send(404, {"error": "unrouted"})

    def do_DELETE(self):
        if self._injected_failure():
            return
        m = _EVENTS_RE.search(self.path)
        if m and m.group(2):
            if EVENTS.pop((m.group(1).lower(), m.group(2)), None) is None:
                return self._send(404, {"error": "not found"})
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._send(404, {"error": "unrouted"})

    def do_PATCH(self):
        if self._injected_failure():
            return
        body = self._body()
        m = _EVENTS_RE.search(self.path)
        if m and m.group(2):
            key = (m.group(1).lower(), m.group(2))
            if key not in EVENTS:
                return self._send(404, {"error": "not found"})
            EVENTS[key].update(body)
            return self._send(200, EVENTS[key])
        mid = self.path.rsplit("/", 1)[-1]
        for m in INBOX:
            if m["id"] == mid:
                m["isRead"] = bool(body.get("isRead"))
        self._send(200)


if __name__ == "__main__":
    print("fake Graph on http://localhost:9911")
    HTTPServer((os.environ.get("FAKE_GRAPH_HOST", "127.0.0.1"), 9911), Handler).serve_forever()
