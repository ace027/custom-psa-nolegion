from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Role = Literal["admin", "tech", "billing", "read_only"]
OrgStatus = Literal["active", "inactive"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorOut(BaseModel):
    detail: str


# ---- organizations ----
class OrganizationIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    status: OrgStatus = "active"
    billing_address: str | None = None
    notes: str | None = None


class OrganizationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: OrgStatus | None = None
    billing_address: str | None = None
    notes: str | None = None


class OrganizationOut(ORM):
    id: int
    name: str
    status: str
    billing_address: str | None
    notes: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---- sites ----
class SiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    notes: str | None = None


class SitePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    notes: str | None = None


class SiteOut(ORM):
    id: int
    organization_id: int
    name: str
    address_line1: str | None
    address_line2: str | None
    city: str | None
    state: str | None
    postal_code: str | None
    notes: str | None
    archived_at: datetime | None


# ---- contacts ----
class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = None
    title: str | None = None
    site_id: int | None = None
    is_primary: bool = False
    is_billing_contact: bool = False


class ContactPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = None
    title: str | None = None
    site_id: int | None = None
    is_primary: bool | None = None
    is_billing_contact: bool | None = None


class ContactOut(ORM):
    id: int
    organization_id: int
    site_id: int | None
    name: str
    email: str | None
    phone: str | None
    title: str | None
    is_primary: bool
    is_billing_contact: bool
    archived_at: datetime | None


# ---- users ----
class UserIn(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)
    role: Role


class UserPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: Role | None = None
    is_active: bool | None = None


class UserOut(ORM):
    id: int
    email: str
    display_name: str
    role: str
    is_active: bool
    last_login_at: datetime | None


class MeOut(UserOut):
    permissions: list[str]


class DevLoginIn(BaseModel):
    email: EmailStr


# ---- audit ----
class AuditOut(ORM):
    id: int
    occurred_at: datetime
    actor_type: str
    actor_id: int | None
    action: str
    entity_type: str | None
    entity_id: int | None
    organization_id: int | None
    before: dict | None
    after: dict | None
    detail: dict | None
    request_id: str | None
    ip: str | None
