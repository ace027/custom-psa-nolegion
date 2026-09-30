"""Microsoft Graph mail client (application permissions, ONE mailbox).

Deliberately small: httpx + the OAuth2 client-credentials flow. No SDK.
The rest of the app talks to the `MailClient` protocol so tests use a fake.
"""

import base64
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

import httpx

log = logging.getLogger("psa.mail")


class GraphError(Exception):
    pass


@dataclass
class InboundMessage:
    id: str
    internet_message_id: str | None
    conversation_id: str | None
    subject: str
    from_email: str | None
    to_emails: list[str]
    body_text: str
    received_at: datetime | None
    headers: dict[str, str] = field(default_factory=dict)  # lower-cased names
    has_attachments: bool = False


@dataclass
class InboundAttachment:
    id: str
    name: str
    content_type: str | None
    size: int
    content: bytes


class MailClient(Protocol):
    def list_unread(self, top: int = 25) -> list[InboundMessage]: ...
    def get_attachments(self, message_id: str, max_bytes: int) -> list[InboundAttachment]: ...
    def mark_read(self, message_id: str) -> None: ...
    def send_mail(
        self,
        to: list[str],
        subject: str,
        body_text: str,
        attachments: list[tuple[str, str, bytes]] | None = None,
    ) -> None: ...


def _addr(obj: dict | None) -> str | None:
    address = ((obj or {}).get("emailAddress") or {}).get("address")
    return address.strip().lower() if address else None


def parse_message(raw: dict) -> InboundMessage:
    headers = {
        h["name"].lower(): h.get("value", "")
        for h in raw.get("internetMessageHeaders") or []
        if "name" in h
    }
    received = raw.get("receivedDateTime")
    return InboundMessage(
        id=raw["id"],
        internet_message_id=raw.get("internetMessageId"),
        conversation_id=raw.get("conversationId"),
        subject=raw.get("subject") or "",
        from_email=_addr(raw.get("from")) or _addr(raw.get("sender")),
        to_emails=[a for a in (_addr(r) for r in raw.get("toRecipients") or []) if a],
        body_text=(raw.get("body") or {}).get("content") or "",
        received_at=datetime.fromisoformat(received.replace("Z", "+00:00")) if received else None,
        headers=headers,
        has_attachments=bool(raw.get("hasAttachments")),
    )


class GraphClient:
    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        mailbox: str,
        http: httpx.Client | None = None,
        base_url: str = "https://graph.microsoft.com/v1.0",
        login_url: str = "https://login.microsoftonline.com",
    ):
        self.tenant_id, self.client_id, self.client_secret = tenant_id, client_id, client_secret
        self.mailbox = mailbox
        self.base_url, self.login_url = base_url.rstrip("/"), login_url.rstrip("/")
        self.http = http or httpx.Client(timeout=30)
        self._resource = self.base_url.split("/v", 1)[0]  # e.g. https://graph.microsoft.com
        self._token: str | None = None
        self._token_expires = 0.0

    # -- auth --
    def _auth(self) -> dict[str, str]:
        if not self._token or time.time() > self._token_expires - 60:
            r = self.http.post(
                f"{self.login_url}/{self.tenant_id}/oauth2/v2.0/token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": f"{self._resource}/.default",
                    "grant_type": "client_credentials",
                },
            )
            if r.status_code != 200:
                raise GraphError(f"token request failed: {r.status_code} {r.text[:300]}")
            body = r.json()
            self._token = body["access_token"]
            self._token_expires = time.time() + int(body.get("expires_in", 3600))
        return {"Authorization": f"Bearer {self._token}"}

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        headers = {**self._auth(), **kw.pop("headers", {})}
        r = self.http.request(
            method, f"{self.base_url}/users/{self.mailbox}{path}", headers=headers, **kw
        )
        if r.status_code >= 400:
            raise GraphError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        return r

    # -- MailClient --
    def list_unread(self, top: int = 25) -> list[InboundMessage]:
        r = self._request(
            "GET",
            "/mailFolders/inbox/messages",
            params={
                "$filter": "isRead eq false",
                "$top": str(top),
                "$select": "id,internetMessageId,conversationId,subject,from,sender,"
                "toRecipients,body,receivedDateTime,hasAttachments,"
                "internetMessageHeaders",
            },
            headers={"Prefer": 'outlook.body-content-type="text"'},
        )
        messages = [parse_message(m) for m in r.json().get("value", [])]
        return sorted(messages, key=lambda m: m.received_at or datetime.min.replace(tzinfo=UTC))

    def get_attachments(self, message_id: str, max_bytes: int) -> list[InboundAttachment]:
        r = self._request("GET", f"/messages/{message_id}/attachments")
        out = []
        for a in r.json().get("value", []):
            if a.get("@odata.type") != "#microsoft.graph.fileAttachment":
                continue  # item/reference attachments are not stored
            size = int(a.get("size") or 0)
            if size > max_bytes:
                log.warning("skipping oversized attachment %s (%s bytes)", a.get("name"), size)
                continue
            if a.get("contentBytes"):
                content = base64.b64decode(a["contentBytes"])
            else:
                content = self._request(
                    "GET", f"/messages/{message_id}/attachments/{a['id']}/$value"
                ).content
            out.append(
                InboundAttachment(
                    a["id"],
                    a.get("name") or "attachment",
                    a.get("contentType"),
                    len(content),
                    content,
                )
            )
        return out

    def mark_read(self, message_id: str) -> None:
        self._request("PATCH", f"/messages/{message_id}", json={"isRead": True})

    def send_mail(
        self,
        to: list[str],
        subject: str,
        body_text: str,
        attachments: list[tuple[str, str, bytes]] | None = None,
    ) -> None:
        """attachments: (filename, content_type, bytes). Graph inline limit is ~3 MB per file."""
        message: dict = {
            "subject": subject,
            "body": {"contentType": "Text", "content": body_text},
            "toRecipients": [{"emailAddress": {"address": a}} for a in to],
        }
        if attachments:
            message["attachments"] = [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": name,
                    "contentType": content_type,
                    "contentBytes": base64.b64encode(data).decode(),
                }
                for name, content_type, data in attachments
            ]
        self._request("POST", "/sendMail", json={"message": message, "saveToSentItems": True})
