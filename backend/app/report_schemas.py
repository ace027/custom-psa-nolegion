"""Response models for the management reports (see app/report_metrics.py for the definitions)."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    automation_minutes: int
    utilisation_bp: int | None
    billable_bp: int | None


class UtilisationTotalsOut(BaseModel):
    capacity_minutes: int
    logged_minutes: int
    billable_minutes: int
    automation_minutes: int
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


# ---- role dashboards --------------------------------------------------------------------
class MyWeekOut(BaseModel):
    logged_minutes: int
    billable_minutes: int
    capacity_minutes: int
    utilisation_bp: int | None


class MyDashboardOut(BaseModel):
    open_tickets: int
    sla_at_risk: int
    sla_breached: int
    appointments_today: int
    week: MyWeekOut


class AgingBucketsOut(BaseModel):
    current_cents: int
    d1_30_cents: int
    d31_60_cents: int
    d61_90_cents: int
    d90_plus_cents: int


class SlaSummaryOut(BaseModel):
    first_response_met_bp: int | None
    resolution_met_bp: int | None
    n: int


class ManagerDashboardOut(BaseModel):
    revenue_mtd_cents: int
    margin_mtd_cents: int
    margin_mtd_bp: int | None
    ar_total_cents: int
    ar_buckets: AgingBucketsOut
    unbilled_cents: int
    sla_30d: SlaSummaryOut
    team_utilisation_last_week_bp: int | None


# ---- report schedules -------------------------------------------------------------------
ReportName = Literal["sla", "utilisation", "aging", "profitability"]


class ScheduleIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    report: ReportName
    frequency: Literal["weekly", "monthly"]
    weekday: int | None = Field(default=None, ge=0, le=6, description="Weekly: 0 = Monday")
    day_of_month: int | None = Field(default=None, ge=1, le=28, description="Monthly: 1 to 28")
    recipient_user_ids: list[int] = Field(min_length=1, max_length=20)
    active: bool = True


class ScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    report: ReportName | None = None
    frequency: Literal["weekly", "monthly"] | None = None
    weekday: int | None = Field(default=None, ge=0, le=6)
    day_of_month: int | None = Field(default=None, ge=1, le=28)
    recipient_user_ids: list[int] | None = Field(default=None, min_length=1, max_length=20)
    active: bool | None = None


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    report: str
    frequency: str
    weekday: int | None
    day_of_month: int | None
    recipient_user_ids: list[int]
    active: bool
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class ScheduleRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    schedule_id: int
    period_start: date
    period_end: date
    status: str
    recipients: list[str]
    email_message_id: int | None
    detail: str | None
    created_at: datetime
