"""Procurement request and response models. Money is integer cents; markup is basis points."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PRODUCT_CATEGORIES = ("hardware", "software", "license", "other")
Category = Literal["hardware", "software", "license", "other"]
POStatus = Literal["draft", "ordered", "partial", "received", "cancelled"]
InventoryStatus = Literal["in_stock", "delivered", "consumed"]
MAX_CENTS = 1_000_000_000_00
MAX_MARKUP_BP = 100_000


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class _Text(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


# ---- vendors ----
class VendorIn(_Text):
    name: str = Field(min_length=1, max_length=200)
    account_number: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    website: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=10_000)


class VendorPatch(_Text):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    account_number: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    website: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=10_000)
    archived: bool | None = None  # true archives the vendor, false restores it


class VendorOut(_ORM):
    id: int
    name: str
    account_number: str | None
    email: str | None
    phone: str | None
    website: str | None
    notes: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---- purchase orders ----
class PurchaseOrderLineIn(_Text):
    """With a product, description / unit cost / taxable default from the catalog (the service
    answers 409 when neither the request nor the product gives a cost)."""

    product_id: int | None = None
    description: str | None = Field(default=None, max_length=2000)
    quantity: int = Field(gt=0, le=1_000_000)
    unit_cost_cents: int | None = Field(default=None, ge=0, le=MAX_CENTS)
    serialised: bool = False
    billable: bool = True
    taxable: bool | None = None
    markup_bp: int | None = Field(default=None, ge=0, le=MAX_MARKUP_BP)


class PurchaseOrderLinePatch(_Text):
    product_id: int | None = None
    description: str | None = Field(default=None, min_length=1, max_length=2000)
    quantity: int | None = Field(default=None, gt=0, le=1_000_000)
    unit_cost_cents: int | None = Field(default=None, ge=0, le=MAX_CENTS)
    serialised: bool | None = None
    billable: bool | None = None
    taxable: bool | None = None
    markup_bp: int | None = Field(default=None, ge=0, le=MAX_MARKUP_BP)


class PurchaseOrderLineOut(_ORM):
    id: int
    purchase_order_id: int
    position: int
    product_id: int | None
    description: str
    quantity: int
    unit_cost_cents: int
    received_quantity: int
    serialised: bool
    billable: bool
    taxable: bool
    markup_bp: int | None


class PurchaseOrderIn(_Text):
    vendor_id: int
    organization_id: int | None = None
    ordered_on: date | None = None
    expected_on: date | None = None
    vendor_reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=10_000)
    lines: list[PurchaseOrderLineIn] = Field(default_factory=list)


class PurchaseOrderPatch(_Text):
    vendor_id: int | None = None
    organization_id: int | None = None
    ordered_on: date | None = None
    expected_on: date | None = None
    vendor_reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=10_000)
    lines: list[PurchaseOrderLineIn] | None = None


class PurchaseOrderOut(_ORM):
    id: int
    number: str | None
    vendor_id: int
    vendor_name: str | None = None
    organization_id: int | None
    status: POStatus
    ordered_on: date | None
    expected_on: date | None
    vendor_reference: str | None
    notes: str | None
    created_by: int | None
    created_at: datetime
    updated_at: datetime
    lines: list[PurchaseOrderLineOut] = []


# ---- receiving, inventory, delivery ----
class ReceiveIn(_Text):
    line_id: int
    quantity: int = Field(gt=0, le=1_000_000)
    serials: list[str] = Field(default_factory=list)

    @field_validator("serials", mode="before")
    @classmethod
    def _strip_serials(cls, v):
        return [s.strip() if isinstance(s, str) else s for s in v] if isinstance(v, list) else v

    @field_validator("serials")
    @classmethod
    def _serials_ok(cls, v: list[str]) -> list[str]:
        seen = set()
        for s in v:
            if not s:
                raise ValueError("serial numbers must not be blank")
            if len(s) > 120:
                raise ValueError("serial numbers are at most 120 characters")
            key = s.lower()
            if key in seen:
                raise ValueError(f"duplicate serial number: {s}")
            seen.add(key)
        return v


class InventoryItemOut(_ORM):
    id: int
    purchase_order_line_id: int | None
    product_id: int | None
    description: str
    serial_number: str | None
    quantity: int
    unit_cost_cents: int
    status: InventoryStatus
    organization_id: int | None
    organization_name: str | None = None
    asset_id: int | None
    delivered_on: date | None
    markup_bp: int | None
    product_charge_id: int | None
    received_on: date
    notes: str | None
    created_at: datetime
    updated_at: datetime


class DeliverIn(BaseModel):
    organization_id: int
    quantity: int | None = Field(default=None, gt=0, le=1_000_000)
    asset_id: int | None = None
    create_asset: bool = False
    delivered_on: date | None = None

    @model_validator(mode="after")
    def _asset_choice(self):
        if self.asset_id is not None and self.create_asset:
            raise ValueError("choose an existing asset or create one, not both")
        return self


# ---- markup rules ----
class MarkupRuleIn(BaseModel):
    product_id: int | None = None
    category: Category | None = None
    markup_bp: int = Field(ge=0, le=MAX_MARKUP_BP)

    @model_validator(mode="after")
    def _one_target(self):
        if (self.product_id is None) == (self.category is None):
            raise ValueError("set exactly one of product_id or category")
        return self


class MarkupRuleOut(_ORM):
    id: int
    product_id: int | None
    category: Category | None
    markup_bp: int
    created_at: datetime
    updated_at: datetime


class MarkupRulePatch(BaseModel):
    markup_bp: int = Field(ge=0, le=MAX_MARKUP_BP)
