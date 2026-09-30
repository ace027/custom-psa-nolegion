"""A tiny fake of the Microsoft Graph mail endpoints, for trying the mail worker locally
without a tenant. NOT for production. Stores state in memory.

    python dev/fake_graph.py                  # serves on http://localhost:9911
    GRAPH_BASE_URL=http://localhost:9911/v1.0 GRAPH_LOGIN_URL=http://localhost:9911 \
    GRAPH_TENANT_ID=t GRAPH_CLIENT_ID=c GRAPH_CLIENT_SECRET=s MAIL_MAILBOX=support@msp.example.com \
        python -m app.worker

Control endpoints (plain JSON):
    POST /_inject   {"from","subject","body","headers":{...}}   add an unread message to the inbox
    GET  /_sent                                                  messages the PSA sent out
"""

import json
import os
import re
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

INBOX: list[dict] = []
SENT: list[dict] = []


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

    def do_POST(self):
        body = self._body()
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
        if self.path == "/_sent":
            return self._send(200, SENT)
        if "/mailFolders/inbox/messages" in self.path:
            return self._send(200, {"value": [m for m in INBOX if not m["isRead"]]})
        if re.search(r"/messages/[^/]+/attachments", self.path):
            return self._send(200, {"value": []})
        self._send(404, {"error": "unrouted"})

    def do_PATCH(self):
        body = self._body()
        mid = self.path.rsplit("/", 1)[-1]
        for m in INBOX:
            if m["id"] == mid:
                m["isRead"] = bool(body.get("isRead"))
        self._send(200)


if __name__ == "__main__":
    print("fake Graph on http://localhost:9911")
    HTTPServer((os.environ.get("FAKE_GRAPH_HOST", "127.0.0.1"), 9911), Handler).serve_forever()
