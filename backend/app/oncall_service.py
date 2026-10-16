"""On-call rotations, overrides and the who-is-on-call views. The oncall_* tables are staff-internal
like user_time_off (no organization_id, no RLS); every write is audited in the same transaction."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select

from app import audit, oncall
from app import repositories as repo
from app import ticket_services as tsvc
from app.deps import Ctx
from app.errors import NotFound
from app.models import OncallMember, OncallOverride, OncallRotation, User

MAX_SCHEDULE_WINDOW = timedelta(days=31)


class InvalidOncall(ValueError):
    """A request the API answers with 422."""


# ---- helpers ----------------------------------------------------------------------------------
def _tz(ctx: Ctx) -> ZoneInfo:
    try:
        return ZoneInfo(repo.get_settings_row(ctx.db).timezone)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return ZoneInfo("UTC")


def _check_users(ctx: Ctx, user_ids: list[int]) -> None:
    if not user_ids:
        return
    active = set(
        ctx.db.execute(
            select(User.id).where(User.id.in_(user_ids), User.is_active.is_(True))
        ).scalars()
    )
    bad = sorted(set(user_ids) - active)
    if bad:
        raise InvalidOncall(f"Unknown or inactive users: {', '.join(map(str, bad))}")


def _names(ctx: Ctx, user_ids: set[int]) -> dict[int, str]:
    if not user_ids:
        return {}
    rows = ctx.db.execute(select(User.id, User.display_name).where(User.id.in_(user_ids)))
    return {uid: name for uid, name in rows}


def _members(ctx: Ctx, rotation_id: int) -> list[OncallMember]:
    return list(
        ctx.db.execute(
            select(OncallMember)
            .where(OncallMember.rotation_id == rotation_id)
            .order_by(OncallMember.position)
        ).scalars()
    )


def _overrides(ctx: Ctx, rotation_id: int) -> list[OncallOverride]:
    return list(
        ctx.db.execute(
            select(OncallOverride)
            .where(OncallOverride.rotation_id == rotation_id)
            .order_by(OncallOverride.starts_at, OncallOverride.id)
        ).scalars()
    )


def get_rotation(ctx: Ctx, rotation_id: int) -> OncallRotation:
    r = ctx.db.get(OncallRotation, rotation_id)
    if r is None:
        raise NotFound("Rotation not found")
    return r


def _snapshot(ctx: Ctx, r: OncallRotation) -> dict:
    snap = {k: v.isoformat() if isinstance(v, time) else v for k, v in audit.snapshot(r).items()}
    return {**snap, "member_ids": [m.user_id for m in _members(ctx, r.id)]}


def rotation_view(ctx: Ctx, r: OncallRotation) -> dict:
    members = _members(ctx, r.id)
    names = _names(ctx, {m.user_id for m in members})
    return dict(
        id=r.id,
        name=r.name,
        handoff_weekday=r.handoff_weekday,
        handoff_time=r.handoff_time,
        anchor_date=r.anchor_date,
        active=r.active,
        members=[
            dict(user_id=m.user_id, name=names.get(m.user_id, ""), position=m.position)
            for m in members
        ],
    )


def override_view(ctx: Ctx, o: OncallOverride) -> dict:
    return override_views(ctx, [o])[0]


def override_views(ctx: Ctx, rows: list[OncallOverride]) -> list[dict]:
    names = _names(ctx, {o.user_id for o in rows})
    return [
        dict(
            id=o.id,
            rotation_id=o.rotation_id,
            user_id=o.user_id,
            user_name=names.get(o.user_id),
            starts_at=o.starts_at,
            ends_at=o.ends_at,
            reason=o.reason,
            created_at=o.created_at,
        )
        for o in rows
    ]


def _set_members(ctx: Ctx, rotation_id: int, member_ids: list[int]) -> None:
    for m in _members(ctx, rotation_id):
        ctx.db.delete(m)
    ctx.db.flush()  # free the (rotation, position) and (rotation, user) slots before re-adding
    for pos, uid in enumerate(member_ids):
        ctx.db.add(OncallMember(rotation_id=rotation_id, user_id=uid, position=pos))
    ctx.db.flush()


# ---- rotations --------------------------------------------------------------------------------
def list_rotations(ctx: Ctx) -> list[dict]:
    rows = ctx.db.execute(select(OncallRotation).order_by(OncallRotation.id)).scalars()
    return [rotation_view(ctx, r) for r in rows]


def create_rotation(ctx: Ctx, data: dict) -> dict:
    member_ids = list(data.get("member_ids") or [])
    _check_users(ctx, member_ids)
    r = OncallRotation(
        name=data["name"].strip(),
        handoff_weekday=data["handoff_weekday"],
        handoff_time=data["handoff_time"],
        anchor_date=data["anchor_date"],
    )
    ctx.db.add(r)
    ctx.db.flush()
    _set_members(ctx, r.id, member_ids)
    ctx.db.refresh(r)
    audit.record(ctx.db, ctx.user, "oncall.rotation_create", r, after=_snapshot(ctx, r))
    return rotation_view(ctx, r)


def update_rotation(ctx: Ctx, rotation_id: int, data: dict) -> dict:
    r = get_rotation(ctx, rotation_id)
    before = _snapshot(ctx, r)
    member_ids = data.pop("member_ids", None)
    for key in ("name", "handoff_weekday", "handoff_time", "anchor_date", "active"):
        if data.get(key) is not None:
            setattr(r, key, data[key].strip() if key == "name" else data[key])
    if r.anchor_date.weekday() != r.handoff_weekday:
        raise InvalidOncall("anchor_date must fall on the handoff weekday (0 = Monday)")
    if member_ids is not None:
        _check_users(ctx, member_ids)
        _set_members(ctx, r.id, member_ids)
    ctx.db.flush()
    ctx.db.refresh(r)
    audit.record(
        ctx.db, ctx.user, "oncall.rotation_update", r, before=before, after=_snapshot(ctx, r)
    )
    return rotation_view(ctx, r)


# ---- overrides --------------------------------------------------------------------------------
def list_overrides(ctx: Ctx, rotation_id: int) -> list[dict]:
    get_rotation(ctx, rotation_id)
    return override_views(ctx, _overrides(ctx, rotation_id))


def create_override(ctx: Ctx, rotation_id: int, data: dict) -> dict:
    get_rotation(ctx, rotation_id)
    _check_users(ctx, [data["user_id"]])
    o = OncallOverride(
        rotation_id=rotation_id,
        user_id=data["user_id"],
        starts_at=data["starts_at"],
        ends_at=data["ends_at"],
        reason=(data.get("reason") or "").strip() or None,
    )
    ctx.db.add(o)
    ctx.db.flush()
    ctx.db.refresh(o)
    audit.record(ctx.db, ctx.user, "oncall.override_create", o, after=audit.snapshot(o))
    return override_view(ctx, o)


def delete_override(ctx: Ctx, override_id: int) -> None:
    o = ctx.db.get(OncallOverride, override_id)
    if o is None:
        raise NotFound("Override not found")
    before = audit.snapshot(o)
    ctx.db.delete(o)
    ctx.db.flush()
    audit.record(ctx.db, ctx.user, "oncall.override_delete", o, before=before)


# ---- who is on call ---------------------------------------------------------------------------
def _active_rotations(ctx: Ctx) -> list[OncallRotation]:
    return list(
        ctx.db.execute(
            select(OncallRotation)
            .where(OncallRotation.active.is_(True))
            .order_by(OncallRotation.id)
        ).scalars()
    )


def now(ctx: Ctx, at: datetime | None = None) -> list[dict]:
    at = at or tsvc.now()
    tz = _tz(ctx)
    rotations = _active_rotations(ctx)
    try:
        found = {
            r.id: oncall.who_is_on(r, _members(ctx, r.id), _overrides(ctx, r.id), at, tz)
            for r in rotations
        }
    except OverflowError:
        raise InvalidOncall("That date is outside the supported range") from None
    names = _names(ctx, {f[0] for f in found.values() if f})
    out = []
    for r in rotations:
        f = found[r.id]
        out.append(
            dict(
                rotation_id=r.id,
                rotation_name=r.name,
                user_id=f[0] if f else None,
                user_name=names.get(f[0]) if f else None,
                until=f[2] if f else None,
                source=f[1] if f else None,
            )
        )
    return out


def schedule(ctx: Ctx, start: datetime, end: datetime) -> list[dict]:
    if start.tzinfo is None or end.tzinfo is None:
        raise InvalidOncall("start and end must include a timezone offset")
    start, end = start.astimezone(UTC), end.astimezone(UTC)
    if end <= start:
        raise InvalidOncall("end must be after start")
    if end - start > MAX_SCHEDULE_WINDOW:
        raise InvalidOncall("The window can be at most 31 days")
    tz = _tz(ctx)
    rows = []
    try:
        for r in _active_rotations(ctx):
            rows += [
                (r.id, s)
                for s in oncall.shifts(
                    r, _members(ctx, r.id), _overrides(ctx, r.id), start, end, tz
                )
            ]
    except OverflowError:
        raise InvalidOncall("That date range is outside the supported range") from None
    names = _names(ctx, {s.user_id for _, s in rows})
    rows.sort(key=lambda x: (x[1].starts_at, x[0]))
    return [
        dict(
            rotation_id=rid,
            user_id=s.user_id,
            user_name=names.get(s.user_id),
            starts_at=s.starts_at,
            ends_at=s.ends_at,
            source=s.source,
        )
        for rid, s in rows
    ]
