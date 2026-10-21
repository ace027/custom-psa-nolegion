"""CRM request and response models. Money is integer cents (forecast estimates, never billed)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

LeadStatus = Literal["new", "contacted", "qualified", "disqualified", "converted"]
OppKind = Literal["new", "renewal", "upsell"]
StageKind = Literal["open", "won", "lost"]
ReminderStatus = Literal["open", "done", "dismissed"]
MAX_CENTS = 1_000_000_000_00


class _ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class _Text(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


# ---- leads ----
class LeadIn(_Text):
    name: str = Field(min_length=1, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    source: str | None = Field(default=None, max_length=100)
    status: Literal["new", "contacted", "qualified", "disqualified"] = "new"
    owner_id: int | None = None
    notes: str | None = Field(default=None, max_length=10_000)


class LeadPatch(_Text):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    source: str | None = Field(default=None, max_length=100)
    status: Literal["new", "contacted", "qualified", "disqualified"] | None = None
    owner_id: int | None = None
    notes: str | None = Field(default=None, max_length=10_000)


class LeadOut(_ORM):
    id: int
    name: str
    company: str | None
    email: str | None
    phone: str | None
    source: str | None
    status: LeadStatus
    owner_id: int | None
    owner_name: str | None = None
    notes: str | None
    converted_organization_id: int | None
    converted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LeadConvert(_Text):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    monthly_cents: int = Field(default=0, ge=0, le=MAX_CENTS)
    term_months: int = Field(default=12, ge=1, le=120)
    expected_close_date: date | None = None
    notes: str | None = Field(default=None, max_length=10_000)


# ---- opportunities ----
class OpportunityIn(_Text):
    organization_id: int
    name: str = Field(min_length=1, max_length=200)
    kind: OppKind = "new"
    stage_id: int | None = None
    owner_id: int | None = None
    monthly_cents: int = Field(default=0, ge=0, le=MAX_CENTS)
    term_months: int = Field(default=12, ge=1, le=120)
    expected_close_date: date | None = None
    notes: str | None = Field(default=None, max_length=10_000)


class OpportunityPatch(_Text):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    owner_id: int | None = None
    monthly_cents: int | None = Field(default=None, ge=0, le=MAX_CENTS)
    term_months: int | None = Field(default=None, ge=1, le=120)
    expected_close_date: date | None = None
    notes: str | None = Field(default=None, max_length=10_000)


class StageMove(_Text):
    stage_id: int
    lost_reason: str | None = Field(default=None, max_length=300)


class QuoteLink(BaseModel):
    quote_id: int


class OpportunityOut(_ORM):
    id: int
    organization_id: int
    organization_name: str
    name: str
    kind: OppKind
    stage_id: int
    stage_name: str
    stage_kind: StageKind
    probability_bp: int
    owner_id: int | None
    owner_name: str | None = None
    monthly_cents: int
    term_months: int
    expected_close_date: date | None
    quote_id: int | None
    quote_number: str | None = None
    agreement_id: int | None
    agreement_name: str | None = None
    lost_reason: str | None
    closed_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


# ---- stages ----
class StageIn(_Text):
    name: str = Field(min_length=1, max_length=100)
    position: int = Field(ge=0, le=10_000)
    probability_bp: int = Field(ge=0, le=10_000, description="5000 = 50%")
    kind: StageKind = "open"
    active: bool = True


class StagePatch(_Text):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    position: int | None = Field(default=None, ge=0, le=10_000)
    probability_bp: int | None = Field(default=None, ge=0, le=10_000)
    active: bool | None = None


class StageOut(_ORM):
    id: int
    name: str
    position: int
    probability_bp: int
    kind: StageKind
    active: bool


# ---- forecast ----
class ForecastBucket(BaseModel):
    key: str
    label: str
    count: int
    monthly_cents: int
    weighted_monthly_cents: int
    contract_value_cents: int


class ForecastOut(BaseModel):
    buckets: list[ForecastBucket]
    total: ForecastBucket
    won_this_month: ForecastBucket
    won_this_quarter: ForecastBucket


# ---- renewals ----
class ReminderOut(BaseModel):
    id: int
    organization_id: int
    organization_name: str
    agreement_id: int
    agreement_name: str
    lead_days: int
    due_on: date
    status: ReminderStatus
    opportunity_id: int | None
    created_at: datetime
