from datetime import UTC, datetime, timedelta

from app.mail.graph import InboundAttachment, InboundMessage

MAILBOX = "support@msp.com"
_counter = {"n": 0}


def msg(
    sender="pat@acme.com",
    subject="Printer is broken",
    body="Please help",
    *,
    id=None,
    headers=None,
    attachments=False,
    internet_id=None,
    minutes=0,
):
    _counter["n"] += 1
    n = _counter["n"]
    return InboundMessage(
        id=id or f"AAMk-{n}",
        internet_message_id=internet_id or f"<msg{n}@mail.test>",
        conversation_id=f"conv-{n}",
        subject=subject,
        from_email=sender,
        to_emails=[MAILBOX],
        body_text=body,
        received_at=datetime(2026, 9, 30, 12, tzinfo=UTC) + timedelta(minutes=minutes),
        headers={k.lower(): v for k, v in (headers or {}).items()},
        has_attachments=attachments,
    )


class FakeMail:
    """In-memory stand-in for the Graph mailbox."""

    def __init__(self):
        self.inbox: list[InboundMessage] = []
        self.read: set[str] = set()
        self.sent: list[dict] = []
        self.files: dict[str, list[InboundAttachment]] = {}
        self.fail_send = False
        self.fail_attachments = False
        self.fail_mark_read = False
        self.fail_list = False

    def add(self, m: InboundMessage, files: list[InboundAttachment] | None = None):
        self.inbox.append(m)
        if files:
            m.has_attachments = True
            self.files[m.id] = files
        return m

    # MailClient
    def list_unread(self, top: int = 25):
        if self.fail_list:
            raise RuntimeError("graph down")
        return [m for m in self.inbox if m.id not in self.read][:top]

    def get_attachments(self, message_id, max_bytes):
        if self.fail_attachments:
            raise RuntimeError("attachment download failed")
        return [a for a in self.files.get(message_id, []) if a.size <= max_bytes]

    def mark_read(self, message_id):
        if self.fail_mark_read:
            raise RuntimeError("cannot mark read")
        self.read.add(message_id)

    def send_mail(self, to, subject, body_text, attachments=None):
        if self.fail_send:
            raise RuntimeError("send failed")
        self.sent.append(
            {
                "to": to,
                "subject": subject,
                "body": body_text,
                "attachments": [(n, ct, data) for n, ct, data in (attachments or [])],
            }
        )
