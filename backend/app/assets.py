"""Asset inventory views: effective warranty (with manual overrides), derived status, merging a
device's vendor records into one asset, and the cross-client warranty report.

Warranty status is derived on read and never stored."""

import re
from datetime import date, timedelta

from sqlalchemy import select

from app import audit
from app.billing import today
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.models import Asset, AssetOverride, Integration, Organization
from app.reports import to_csv

OVERRIDE_FIELDS = ("warranty_start", "warranty_end")
STATUSES = ("expired", "expiring_30", "expiring_60", "expiring_90", "in_warranty", "unknown")

# Serial numbers that BIOS/vendors report when nothing is set; matching on them would merge
# unrelated machines.
_JUNK_SERIALS = {
    "0",
    "NONE",
    "NA",
    "NULL",
    "UNKNOWN",
    "DEFAULTSTRING",
    "TOBEFILLEDBYOEM",
    "SYSTEMSERIALNUMBER",
    "123456789",
    "NOTAVAILABLE",
    "NOTSPECIFIED",
    "SERIALNUMBER",
}


def normalize_serial(serial: str | None) -> str | None:
    if not serial:
        return None
    s = re.sub(r"[^A-Z0-9]", "", serial.upper())
    if len(s) < 4 or s in _JUNK_SERIALS or len(set(s)) == 1:
        return None
    return s


def warranty_status(end: date | None, on: date) -> str:
    if end is None:
        return "unknown"
    if end < on:
        return "expired"
    days = (end - on).days
    if days <= 30:
        return "expiring_30"
    if days <= 60:
        return "expiring_60"
    if days <= 90:
        return "expiring_90"
    return "in_warranty"


def effective(asset: Asset, field: str) -> tuple[date | None, bool]:
    """(value, overridden) for warranty_start / warranty_end."""
    for o in asset.overrides:
        if o.field == field:
            return o.value_date, True
    return getattr(asset, field), False


# ---- merging vendor records into one asset ----
_OWNER_ORDER = {"network": ("hudu", "ninjaone")}
_DEFAULT_ORDER = ("ninjaone", "hudu")


def merge(asset: Asset, kinds_by_integration: dict[int, str]) -> None:
    """Recompute the asset's synced fields from its sources.

    Precedence: the system that owns that class of device (NinjaOne for computers and servers,
    Hudu for network gear), then the other. A manual override is applied on read, never here."""
    sources = list(asset.sources)
    if not sources:
        return
    kinds = {s.data.get("kind") for s in sources} - {None, "other"}
    if "network" in kinds:
        kind = "network"
    elif kinds:
        kind = sorted(
            kinds,
            key=lambda k: ("computer", "server").index(k) if k in ("computer", "server") else 9,
        )[0]
    else:
        kind = "other"
    order = _OWNER_ORDER.get(kind, _DEFAULT_ORDER)
    ranked = sorted(
        sources,
        key=lambda s: (
            order.index(kinds_by_integration.get(s.integration_id, ""))
            if kinds_by_integration.get(s.integration_id) in order
            else 99
        ),
    )

    def first(key: str):
        for s in ranked:
            if s.data.get(key):
                return s.data[key]
        return None

    asset.kind = kind
    asset.name = first("name") or asset.name
    asset.manufacturer = first("manufacturer")
    asset.model = first("model")
    asset.serial = first("serial")
    asset.serial_norm = normalize_serial(asset.serial)
    for key in OVERRIDE_FIELDS:
        v = first(key)
        setattr(asset, key, date.fromisoformat(v) if v else None)
    ends = {s.data.get("warranty_end") for s in sources if s.data.get("warranty_end")}
    asset.conflict = len(ends) > 1
    asset.last_seen_at = max(s.last_seen_at for s in sources)


# ---- reading ----
def asset_row(ctx: Ctx, a: Asset, on: date | None = None) -> dict:
    on = on or today(ctx)
    start, start_over = effective(a, "warranty_start")
    end, end_over = effective(a, "warranty_end")
    return {
        "id": a.id,
        "organization_id": a.organization_id,
        "organization_name": a.organization.name,
        "kind": a.kind,
        "name": a.name,
        "manufacturer": a.manufacturer,
        "model": a.model,
        "serial": a.serial,
        "warranty_start": start,
        "warranty_end": end,
        "warranty_status": warranty_status(end, on),
        "warranty_overridden": start_over or end_over,
        "conflict": a.conflict,
        "first_seen_at": a.first_seen_at,
        "last_seen_at": a.last_seen_at,
        "retired_at": a.retired_at,
    }


def _get(ctx: Ctx, asset_id: int) -> Asset:
    a = ctx.db.get(Asset, asset_id)
    if a is None or not ctx.scope.allows(a.organization_id):
        raise NotFound("Asset not found")
    return a


def list_assets(ctx: Ctx, org_id: int, include_retired: bool = False) -> list[dict]:
    q = select(Asset).where(Asset.organization_id == org_id).order_by(Asset.kind, Asset.name)
    if not include_retired:
        q = q.where(Asset.retired_at.is_(None))
    on = today(ctx)
    return [
        asset_row(ctx, a, on) for a in ctx.db.scalars(ctx.scope.apply(q, Asset.organization_id))
    ]


def asset_detail(ctx: Ctx, asset_id: int) -> dict:
    a = _get(ctx, asset_id)
    names = {i.id: i.name for i in ctx.db.scalars(select(Integration))}
    out = asset_row(ctx, a)
    out["sources"] = [
        {
            "integration": names.get(s.integration_id, "?"),
            "external_id": s.external_id,
            "data": s.data,
            "last_seen_at": s.last_seen_at,
        }
        for s in a.sources
    ]
    out["overrides"] = [
        {
            "field": o.field,
            "value": o.value_date,
            "reason": o.reason,
            "created_by": o.created_by,
            "updated_at": o.updated_at,
        }
        for o in a.overrides
    ]
    return out


def set_override(ctx: Ctx, asset_id: int, field: str, value: date, reason: str) -> dict:
    a = _get(ctx, asset_id)
    if field not in OVERRIDE_FIELDS:
        raise Conflict("Only warranty start and end dates can be corrected")
    if not reason.strip():
        raise Conflict("A reason is required")
    existing = next((o for o in a.overrides if o.field == field), None)
    before = (
        {"value": existing.value_date.isoformat(), "reason": existing.reason} if existing else None
    )
    if existing:
        existing.value_date, existing.reason = value, reason.strip()
        existing.created_by = ctx.user.id if ctx.user else None
    else:
        a.overrides.append(
            AssetOverride(
                organization_id=a.organization_id,
                field=field,
                value_date=value,
                reason=reason.strip(),
                created_by=ctx.user.id if ctx.user else None,
            )
        )
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "asset.override_set",
        a,
        organization_id=a.organization_id,
        before=before,
        after={"field": field, "value": value.isoformat(), "reason": reason.strip()},
    )
    return asset_detail(ctx, a.id)


def clear_override(ctx: Ctx, asset_id: int, field: str) -> dict:
    a = _get(ctx, asset_id)
    existing = next((o for o in a.overrides if o.field == field), None)
    if existing is None:
        raise NotFound("No override on that field")
    before = {"field": field, "value": existing.value_date.isoformat(), "reason": existing.reason}
    a.overrides.remove(existing)
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "asset.override_cleared",
        a,
        organization_id=a.organization_id,
        before=before,
    )
    return asset_detail(ctx, a.id)


# ---- warranty report ----
def warranty_report(
    ctx: Ctx,
    organization_id: int | None = None,
    status: str | None = None,
    within_days: int | None = None,
) -> dict:
    """Active (not retired) assets of active clients, soonest expiry first. `status` filters to one
    derived status; `within_days` keeps expired plus those expiring inside the window."""
    if status is not None and status not in STATUSES:
        raise Conflict(f"status must be one of {', '.join(STATUSES)}")
    on = today(ctx)
    q = (
        select(Asset)
        .join(Organization, Organization.id == Asset.organization_id)
        .where(Asset.retired_at.is_(None), Organization.status == "active")
    )
    if organization_id:
        q = q.where(Asset.organization_id == organization_id)
    rows = [
        asset_row(ctx, a, on) for a in ctx.db.scalars(ctx.scope.apply(q, Asset.organization_id))
    ]
    if status:
        rows = [r for r in rows if r["warranty_status"] == status]
    if within_days is not None:
        limit = on + timedelta(days=within_days)
        rows = [r for r in rows if r["warranty_end"] is not None and r["warranty_end"] <= limit]
    rows.sort(
        key=lambda r: (
            r["warranty_end"] is None,
            r["warranty_end"] or date.max,
            r["organization_name"],
            r["name"],
        )
    )
    counts = {s: 0 for s in STATUSES}
    for r in rows:
        counts[r["warranty_status"]] += 1
    return {"as_of": on, "total": len(rows), "counts": counts, "rows": rows}


def warranty_csv(report: dict) -> str:
    header = [
        "Client",
        "Device",
        "Type",
        "Manufacturer",
        "Model",
        "Serial",
        "Warranty end",
        "Status",
        "Corrected by a tech",
        "Sources disagree",
    ]
    rows = [
        [
            r["organization_name"],
            r["name"],
            r["kind"],
            r["manufacturer"],
            r["model"],
            r["serial"],
            r["warranty_end"],
            r["warranty_status"],
            "yes" if r["warranty_overridden"] else "",
            "yes" if r["conflict"] else "",
        ]
        for r in report["rows"]
    ]
    return to_csv(header, rows)
