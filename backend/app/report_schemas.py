"""Response models for the management reports (see app/report_metrics.py for the definitions)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class RangeOut(BaseModel):
    start: date
    end: date


class SlaClockOut(BaseModel):
    met: int
    breached: int
    pending: int
    no_sla: int
    met_bp: int | None
    p50_minutes: int | None
    p90_minutes: int | None


class SlaRowOut(BaseModel):
    key: int | None
    label: str
    n: int
    first_response: SlaClockOut
    resolution: SlaClockOut


class SlaTotalsOut(BaseModel):
    n: int
    first_response: SlaClockOut
    resolution: SlaClockOut


class SlaReportOut(BaseModel):
    range: RangeOut
    group: Literal["priority", "organization", "assignee"]
    rows: list[SlaRowOut]
    totals: SlaTotalsOut


class UtilisationRowOut(BaseModel):
    user_id: int
    name: str
    capacity_minutes: int
    logged_minutes: int
    billable_minutes: int
    utilisation_bp: int | None
    billable_bp: int | None


class UtilisationTotalsOut(BaseModel):
    capacity_minutes: int
    logged_minutes: int
    billable_minutes: int
    utilisation_bp: int | None
    billable_bp: int | None


class UtilisationReportOut(BaseModel):
    range: RangeOut
    rows: list[UtilisationRowOut]
    totals: UtilisationTotalsOut


class AgingRowOut(BaseModel):
    organization_id: int
    organization_name: str
    current_cents: int
    d1_30_cents: int
    d31_60_cents: int
    d61_90_cents: int
    d90_plus_cents: int
    total_open_cents: int
    credit_cents: int
    open_invoice_count: int
    overdue_invoice_count: int
    oldest_days_past_due: int


class AgingReportOut(BaseModel):
    as_of: date
    rows: list[AgingRowOut]
    totals: AgingRowOut


class ProfitabilityTotalsOut(BaseModel):
    revenue_cents: int
    labour_cost_cents: int
    goods_cost_cents: int
    expense_cost_cents: int
    cost_cents: int
    margin_cents: int
    margin_bp: int | None
    minutes_without_cost_rate: int
    charges_without_cost: int


class ProfitabilityRowOut(ProfitabilityTotalsOut):
    organization_id: int
    organization_name: str


class ProfitabilityReportOut(BaseModel):
    range: RangeOut
    rows: list[ProfitabilityRowOut]
    totals: ProfitabilityTotalsOut


class CostRateIn(BaseModel):
    cost_rate_cents: int | None = Field(
        ge=0, description="Hourly internal cost of this person's time in cents; null clears it"
    )


class CostRateOut(BaseModel):
    user_id: int
    cost_rate_cents: int | None
