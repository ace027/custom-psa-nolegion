"""Schemas for the Phase 14 client-portal additions (SSO, attachments, self-service, exports)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PortalLoginOptionsOut(BaseModel):
    sso: bool  # "Sign in with Microsoft" is configured and the portal is turned on


class PortalAttachmentIn(BaseModel):
    filename: str = Field(min_length=1, max_length=300)
    # The size cap comes from settings.max_attachment_bytes: the request body is bounded before it
    # is parsed (portal_files.SizeLimitedRoute) and the decoded size is re-checked in _decode.
    content_base64: str = Field(min_length=1)


class PortalAttachmentOut(BaseModel):
    id: int
    filename: str
    size_bytes: int
    created_at: datetime


class PortalContactPatch(BaseModel):
    """What a contact may change about themselves. Email is deliberately absent (extra=forbid)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    title: str | None = Field(default=None, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("phone", "title", mode="before")
    @classmethod
    def _blank_to_none(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v
