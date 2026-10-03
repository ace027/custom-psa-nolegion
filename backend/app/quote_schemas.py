"""API shapes for surveys, quotes and the rate card."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

DeviceClass = Literal["workstation", "server", "network", "other"]
WarrantyStatus = Literal["in_warranty", "out_of_warranty", "unknown"]
SurveyStatus = Literal["scheduled", "in_progress", "completed"]
QuoteStatus = Literal[
    "draft", "needs_approval", "approved", "sent", "accepted", "declined", "cancelled"
]
CENTS = {"default": None, "ge": 0, "le": 10_000_000_00}
BP = {"default": None, "ge": 0, "le": 100_000}


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class QuoteSettingsOut(ORM):
    per_user_rate_cents: int
    workstation_rate_cents: int
    server_rate_cents: int
    network_rate_cents: int
    other_rate_cents: int
    hardware_uplift_bp: int
    server_uplift_bp: int
    legacy_app_uplift_bp: int
    term_months: int
    valid_days: int
    agreement_taxable: bool
    intro_text: str | None


class QuoteSettingsPatch(BaseModel):
    per_user_rate_cents: int | None = Field(**CENTS)
    workstation_rate_cents: int | None = Field(**CENTS)
    server_rate_cents: int | None = Field(**CENTS)
    network_rate_cents: int | None = Field(**CENTS)
    other_rate_cents: int | None = Field(**CENTS)
    hardware_uplift_bp: int | None = Field(**BP)
    server_uplift_bp: int | None = Field(**BP)
    legacy_app_uplift_bp: int | None = Field(**BP)
    term_months: int | None = Field(default=None, ge=1, le=120)
    valid_days: int | None = Field(default=None, ge=1, le=365)
    agreement_taxable: bool | None = None
    intro_text: str | None = Field(default=None, max_length=4000)


# ---- surveys ----
class SurveyCreate(BaseModel):
    scheduled_for: datetime | None = None
    tech_id: int | None = None
    notes: str | None = Field(default=None, max_length=10000)


class SurveyDeviceIn(BaseModel):
    device_class: DeviceClass
    label: str | None = Field(default=None, max_length=200)
    make_model: str | None = Field(default=None, max_length=200)
    serial: str | None = Field(default=None, max_length=100)
    warranty_end: date | None = None
    warranty_status: WarrantyStatus = "unknown"
    priced: bool = True
    notes: str | None = Field(default=None, max_length=2000)


class SurveyDeviceOut(SurveyDeviceIn, ORM):
    id: int


class SurveyAppIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    vendor: str | None = Field(default=None, max_length=200)
    legacy: bool = False
    notes: str | None = Field(default=None, max_length=2000)


class SurveyAppOut(SurveyAppIn, ORM):
    id: int


class SurveySave(BaseModel):
    user_count: int = Field(ge=0, le=100_000)
    site_count: int = Field(default=1, ge=0, le=10_000)
    notes: str | None = Field(default=None, max_length=10000)
    scheduled_for: datetime | None = None
    tech_id: int | None = None
    devices: list[SurveyDeviceIn] = Field(default_factory=list, max_length=2000)
    apps: list[SurveyAppIn] = Field(default_factory=list, max_length=200)


class SurveyOut(ORM):
    id: int
    organization_id: int
    organization_name: str = ""  # filled in by the router
    status: SurveyStatus
    scheduled_for: datetime | None
    tech_id: int | None
    user_count: int
    site_count: int
    notes: str | None
    completed_at: datetime | None
    created_at: datetime
    devices: list[SurveyDeviceOut]
    apps: list[SurveyAppOut]


# ---- quotes ----
class QuoteCreate(BaseModel):
    kind: Literal["new", "reprice"] = "new"
    agreement_id: int | None = None  # reprice: the flat agreement being replaced
    effective_date: date | None = None  # reprice: first day of a future month
    notes: str | None = Field(default=None, max_length=4000)


class QuotePatch(BaseModel):
    final_price_cents: int | None = Field(**CENTS)
    adjustment_reason: str | None = Field(default=None, max_length=2000)
    valid_until: date | None = None
    effective_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)


class NoteIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


class OptionalNoteIn(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class QuoteSend(BaseModel):
    send_email: bool = False
    to_emails: list[EmailStr] | None = Field(default=None, max_length=10)


class QuoteAccept(BaseModel):
    start_date: date | None = None  # new client: contract start (default today)
    note: str | None = Field(default=None, max_length=2000)


class QuoteOut(ORM):
    id: int
    number: str
    organization_id: int
    organization_name: str
    survey_id: int
    kind: str
    agreement_id: int | None
    version: int
    replaces_quote_id: int | None
    status: QuoteStatus
    is_expired: bool
    snapshot: dict
    base_cents: int
    uplift_bp: int
    computed_price_cents: int
    final_price_cents: int
    adjustment_reason: str | None
    adjusted_by: int | None
    term_months: int
    valid_until: date | None
    effective_date: date | None
    notes: str | None
    decision_note: str | None
    submitted_at: datetime | None
    approved_by: int | None
    approved_at: datetime | None
    sent_at: datetime | None
    sent_to: str | None
    decided_at: datetime | None
    resulting_agreement_id: int | None
    created_at: datetime
