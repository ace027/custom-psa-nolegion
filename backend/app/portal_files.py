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

from fastapi import HTTPException
from sqlalchemy import func, select

from app import audit
from app import portal as svc
from app import ticket_services as tsvc
from app.config import get_settings
from app.errors import NotFound
from app.models import Attachment
from app.portal_deps import PortalCtx

MAX_UPLOADS_PER_HOUR = 20
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


def safe_filename(name: str) -> str:
    """Strip any path components, then the same rule the staff download applies."""
    base = re.split(r"[\\/]", name or "")[-1]
    return re.sub(r"[^\w.\- ]", "_", base).lstrip(".").strip()[:300] or "attachment"


def _decode(content_base64: str, max_bytes: int) -> bytes:
    # base64 inflates by 4/3: reject a huge body before spending memory on decoding it
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
    data = _decode(content_base64, settings.max_attachment_bytes)
    since = tsvc.now() - timedelta(hours=1)
    recent = ctx.db.execute(
        select(func.count())
        .select_from(Attachment)
        .where(Attachment.uploaded_by_contact_id == ctx.contact.id, Attachment.created_at > since)
    ).scalar_one()
    if recent >= MAX_UPLOADS_PER_HOUR:
        raise HTTPException(429, "You have uploaded a lot of files; please try again later")

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
