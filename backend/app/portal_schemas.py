"""Schemas for the Phase 14 client-portal additions (SSO, attachments, self-service, exports)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PortalLoginOptionsOut(BaseModel):
    sso: bool  # "Sign in with Microsoft" is configured and the portal is turned on


class PortalAttachmentIn(BaseModel):
    filename: str = Field(min_length=1, max_length=300)
    # base64 of the default 10 MB cap (4/3 inflation + padding slack); the exact configured cap is
    # re-checked in portal_files._decode
    content_base64: str = Field(min_length=1, max_length=(10 * 1024 * 1024 * 4) // 3 + 8)


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
