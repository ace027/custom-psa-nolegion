"""API shapes for working hours, time off, appointments and availability."""

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

TimeOffStatus = Literal["pending", "approved", "rejected", "cancelled"]
AppointmentStatus = Literal["scheduled", "cancelled"]
ConflictKind = Literal["outside_hours", "time_off", "time_off_pending", "overlap"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- schedule ----
class WorkHoursDay(ORM):
    weekday: int = Field(ge=0, le=6, description="0 = Monday")
    start_minute: int = Field(ge=0, le=1439, description="Minutes from local midnight")
    end_minute: int = Field(ge=1, le=1440, description="Minutes from local midnight; 1440 = 24:00")

    @model_validator(mode="after")
    def _ordered(self):
        if self.start_minute >= self.end_minute:
            raise ValueError("start_minute must be before end_minute")
        return self


class ScheduleOut(BaseModel):
    user_id: int
    timezone: str  # effective: the override, else the Settings timezone
    timezone_override: str | None
    uses_default_hours: bool
    work_hours: list[WorkHoursDay]


class SchedulePut(BaseModel):
    timezone: str | None = Field(default=None, max_length=64, description="null = org timezone")
    work_hours: list[WorkHoursDay] | None = Field(
        default=None, description="null = the org business hours; days not listed are off"
    )

    @field_validator("work_hours")
    @classmethod
    def _days(cls, v: list[WorkHoursDay] | None):
        if v is None:
            return v
        if not v:
            raise ValueError("List at least one working day, or send null to use the org hours")
        days = [d.weekday for d in v]
        if len(days) != len(set(days)):
            raise ValueError("Each weekday can appear only once")
        return sorted(v, key=lambda d: d.weekday)


# ---- time off ----
class TimeOffIn(BaseModel):
    user_id: int | None = None  # default: yourself
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    reason: str | None = Field(default=None, max_length=500)


class TimeOffDecision(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class TimeOffOut(BaseModel):
    id: int
    user_id: int
    user_name: str
    starts_at: datetime
    ends_at: datetime
    reason: str | None  # only for the owner and approvers
    status: TimeOffStatus
    requested_by: int
    decided_by: int | None
    decided_at: datetime | None
    decision_note: str | None
    created_at: datetime


# ---- appointments ----
class AppointmentIn(BaseModel):
    ticket_id: int
    tech_id: int
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    notes: str | None = Field(default=None, max_length=4000)
    client_visible: bool = True


class AppointmentPatch(BaseModel):
    tech_id: int | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    notes: str | None = Field(default=None, max_length=4000)
    client_visible: bool | None = None


class AppointmentCancel(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class Conflict(BaseModel):
    kind: ConflictKind
    time_off_id: int | None = None
    appointment_id: int | None = None


class AppointmentOut(BaseModel):
    id: int
    organization_id: int
    organization_name: str | None
    ticket_id: int
    ticket_number: int | None
    ticket_subject: str | None
    tech_id: int
    tech_name: str | None
    starts_at: datetime
    ends_at: datetime
    status: AppointmentStatus
    notes: str | None
    client_visible: bool
    created_by: int | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    conflicts: list[Conflict] = []  # warnings only; the appointment is saved regardless


# ---- availability ----
class Window(BaseModel):
    starts_at: datetime
    ends_at: datetime


class AppointmentWindow(Window):
    id: int


class AvailabilityOut(BaseModel):
    user_id: int
    timezone: str
    working: list[Window]
    time_off: list[Window]  # approved only
    appointments: list[AppointmentWindow]  # scheduled only
    free: list[Window]
