"""Files a portal contact attaches to their own tickets. The contact can see only what they or
their organization uploaded through the portal; attachments that arrived by email stay internal."""

import base64
import binascii
import hashlib
import mimetypes
import re
import uuid
from datetime import timedelta
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.routing import APIRoute
from sqlalchemy import func, select

from app import audit
from app import portal as svc
from app import ticket_services as tsvc
from app.config import get_settings
from app.errors import NotFound
from app.models import Attachment
from app.portal_deps import PortalCtx

MAX_UPLOADS_PER_HOUR = 20
# pg_advisory_xact_lock(namespace, contact_id): serializes one contact's uploads.
UPLOAD_LOCK_NAMESPACE = 14_003
ALLOWED_EXTENSIONS = frozenset(
    {
        ".txt",
        ".log",
        ".csv",
        ".pdf",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".zip",
        ".eml",
        ".msg",
    }
)


def max_body_bytes() -> int:
    """Largest request body the upload route reads: base64 inflation (4/3) plus JSON overhead."""
    return (get_settings().max_attachment_bytes * 4) // 3 + 1024


class SizeLimitedRoute(APIRoute):
    """Rejects an oversized body with 413 before FastAPI reads it: by Content-Length when the
    client sent one, and by counting bytes as they arrive (chunked bodies may omit the header)."""

    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request):
            limit = max_body_bytes()
            declared = request.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > limit:
                raise HTTPException(413, "That file is too large")
            received = 0
            inner = request.receive

            async def receive():
                nonlocal received
                message = await inner()
                if message["type"] == "http.request":
                    received += len(message.get("body", b""))
                    if received > limit:
                        raise HTTPException(413, "That file is too large")
                return message

            return await original(Request(request.scope, receive))

        return handler


def safe_filename(name: str) -> str:
    """Strip any path components, then the same rule the staff download applies."""
    base = re.split(r"[\\/]", name or "")[-1]
    return re.sub(r"[^\w.\- ]", "_", base).lstrip(".").strip()[:300] or "attachment"


def _decode(content_base64: str, max_bytes: int) -> bytes:
    # base64 inflates by 4/3: reject an oversized string before spending memory on decoding it.
    # The body itself is already bounded by SizeLimitedRoute; this is the exact configured cap.
    if len(content_base64) > (max_bytes * 4) // 3 + 8:
        raise HTTPException(413, "That file is too large")
    try:
        data = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "The file content is not valid base64") from None
    if not data:
        raise HTTPException(422, "The file is empty")
    if len(data) > max_bytes:
        raise HTTPException(413, "That file is too large")
    return data


def _out(a: Attachment) -> dict:
    return dict(id=a.id, filename=a.filename, size_bytes=a.size_bytes, created_at=a.created_at)


def upload(ctx: PortalCtx, ticket_id: int, filename: str, content_base64: str) -> dict:
    t = svc._get_ticket(ctx, ticket_id)
    if t.status == "closed":
        raise HTTPException(409, "This ticket is closed; open a new one")
    settings = get_settings()
    name = safe_filename(filename)
    if Path(name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "That file type is not allowed")
    # Cheap checks first, decoding last. The transaction-scoped lock makes count-then-insert
    # atomic per contact, so parallel requests cannot all pass the hourly limit or the quota.
    ctx.db.execute(select(func.pg_advisory_xact_lock(UPLOAD_LOCK_NAMESPACE, ctx.contact.id)))
    since = tsvc.now() - timedelta(hours=1)
    recent = ctx.db.execute(
        select(func.count())
        .select_from(Attachment)
        .where(Attachment.uploaded_by_contact_id == ctx.contact.id, Attachment.created_at > since)
    ).scalar_one()
    if recent >= MAX_UPLOADS_PER_HOUR:
        raise HTTPException(429, "You have uploaded a lot of files; please try again later")
    used = ctx.db.execute(
        select(func.coalesce(func.sum(Attachment.size_bytes), 0)).where(
            Attachment.organization_id == t.organization_id, Attachment.source == "portal"
        )
    ).scalar_one()
    # Upper bound of the decoded size, known without decoding: 3 bytes per 4 base64 characters.
    if used + (len(content_base64) * 3) // 4 > settings.portal_org_storage_bytes:
        raise HTTPException(413, "This client's file storage is full. Contact us.")
    data = _decode(content_base64, settings.max_attachment_bytes)

    key = f"{t.id}/{uuid.uuid4().hex}"
    path = Path(settings.attachments_dir) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    att = Attachment(
        email_message_id=None,
        ticket_id=t.id,
        organization_id=t.organization_id,
        source="portal",
        uploaded_by_contact_id=ctx.contact.id,
        filename=name,
        content_type=mimetypes.guess_type(name)[0] or "application/octet-stream",
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        storage_key=key,
    )
    ctx.db.add(att)
    try:
        ctx.db.flush()
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    audit.record(
        ctx.db,
        None,
        "portal.attachment_upload",
        att,
        organization_id=t.organization_id,
        detail={"contact_id": ctx.contact.id, "filename": name, "size": len(data)},
    )
    return _out(att)


def list_for_ticket(ctx: PortalCtx, ticket_id: int) -> list[dict]:
    t = svc._get_ticket(ctx, ticket_id)
    rows = ctx.db.execute(
        ctx.scope.apply(
            select(Attachment).where(Attachment.ticket_id == t.id, Attachment.source == "portal"),
            Attachment.organization_id,
        ).order_by(Attachment.id)
    ).scalars()
    return [_out(a) for a in rows]


def get_for_download(ctx: PortalCtx, attachment_id: int) -> tuple[Path, str]:
    att = ctx.db.execute(
        ctx.scope.apply(
            select(Attachment).where(Attachment.id == attachment_id, Attachment.source == "portal"),
            Attachment.organization_id,
        )
    ).scalar_one_or_none()
    if att is None:
        raise NotFound("Attachment not found")
    svc._get_ticket(ctx, att.ticket_id)  # must be a ticket this contact may see
    base = Path(get_settings().attachments_dir).resolve()
    path = (base / att.storage_key).resolve()
    if base not in path.parents or not path.is_file():  # path-traversal guard
        raise NotFound("Attachment file is missing")
    return path, safe_filename(att.filename)
