"""API shapes for on-call rotations, members, overrides and the who-is-on-call views."""

from datetime import date, datetime, time
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, Field, field_validator, model_validator

OnCallSource = Literal["rotation", "override"]


def _anchor_range(v: date | None) -> date | None:
    if v is not None and not 2000 <= v.year <= 2100:
        raise ValueError("anchor_date must be between the years 2000 and 2100")
    return v


def _unique(v: list[int] | None) -> list[int] | None:
    if v is not None and len(v) != len(set(v)):
        raise ValueError("Each member can be listed only once")
    return v


class RotationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    handoff_weekday: int = Field(ge=0, le=6, description="0 = Monday")
    handoff_time: time
    anchor_date: date
    member_ids: list[int] = Field(default=[], description="Ordered; first member is on call first")

    _members = field_validator("member_ids")(_unique)
    _anchor = field_validator("anchor_date")(_anchor_range)

    @model_validator(mode="after")
    def _anchor_weekday(self) -> Self:
        if self.anchor_date.weekday() != self.handoff_weekday:
            raise ValueError(
                "anchor_date must fall on the handoff weekday "
                f"(it is weekday {self.anchor_date.weekday()}, 0 = Monday, "
                f"but handoff_weekday is {self.handoff_weekday})"
            )
        return self


class RotationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    handoff_weekday: int | None = Field(default=None, ge=0, le=6)
    handoff_time: time | None = None
    anchor_date: date | None = None
    active: bool | None = None
    member_ids: list[int] | None = Field(
        default=None, description="Replaces the ordered member list when given"
    )

    _members = field_validator("member_ids")(_unique)
    _anchor = field_validator("anchor_date")(_anchor_range)


class MemberOut(BaseModel):
    user_id: int
    name: str
    position: int


class RotationOut(BaseModel):
    id: int
    name: str
    handoff_weekday: int
    handoff_time: time
    anchor_date: date
    active: bool
    members: list[MemberOut]


class OverrideCreate(BaseModel):
    user_id: int
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class OverrideOut(BaseModel):
    id: int
    rotation_id: int
    user_id: int
    user_name: str | None = None
    starts_at: datetime
    ends_at: datetime
    reason: str | None
    created_at: datetime


class OnCallNowOut(BaseModel):
    rotation_id: int
    rotation_name: str
    user_id: int | None
    user_name: str | None
    until: datetime | None
    source: OnCallSource | None


class ShiftOut(BaseModel):
    rotation_id: int
    user_id: int
    user_name: str | None
    starts_at: datetime
    ends_at: datetime
    source: OnCallSource
