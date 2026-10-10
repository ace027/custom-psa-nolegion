"""Asset inventory and warranty: per-client lists, manual corrections, the cross-client report,
and the per-client switch that publishes the portal page."""

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app import assets as svc
from app import audit
from app import permissions as P
from app.asset_schemas import (
    AssetDetailOut,
    AssetOut,
    OverrideIn,
    SharingIn,
    SharingOut,
    WarrantyReportOut,
)
from app.deps import Ctx, require
from app.errors import NotFound
from app.models import Organization
from app.schemas import ErrorOut

router = APIRouter(tags=["assets"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}


@router.get(
    "/organizations/{org_id}/assets",
    response_model=list[AssetOut],
    responses=ERR,
    summary="A client's devices with derived warranty status",
)
def list_assets(org_id: int, include_retired: bool = False, ctx: Ctx = require(P.ORG_READ)):
    if not ctx.scope.allows(org_id) or ctx.db.get(Organization, org_id) is None:
        raise NotFound("Organization not found")
    return svc.list_assets(ctx, org_id, include_retired)


@router.get(
    "/assets/{asset_id}",
    response_model=AssetDetailOut,
    responses=ERR,
    summary="One device: effective values, vendor records and corrections",
)
def get_asset(asset_id: int, ctx: Ctx = require(P.ORG_READ)):
    return svc.asset_detail(ctx, asset_id)


@router.put(
    "/assets/{asset_id}/overrides/{field}",
    response_model=AssetDetailOut,
    responses=ERR,
    summary="Correct a warranty date (survives every sync; needs a reason)",
)
def set_override(asset_id: int, field: str, body: OverrideIn, ctx: Ctx = require(P.ORG_WRITE)):
    return svc.set_override(ctx, asset_id, field, body.value, body.reason)


@router.delete(
    "/assets/{asset_id}/overrides/{field}",
    response_model=AssetDetailOut,
    responses=ERR,
    summary="Remove a correction and go back to the vendor's value",
)
def clear_override(asset_id: int, field: str, ctx: Ctx = require(P.ORG_WRITE)):
    return svc.clear_override(ctx, asset_id, field)


@router.put(
    "/organizations/{org_id}/assets-sharing",
    response_model=SharingOut,
    responses=ERR,
    summary="Publish (or withdraw) the devices page for a client's portal contacts",
)
def set_sharing(org_id: int, body: SharingIn, ctx: Ctx = require(P.PORTAL_MANAGE)):
    org = ctx.db.get(Organization, org_id)
    if org is None or not ctx.scope.allows(org_id):
        raise NotFound("Organization not found")
    before = {"assets_published": org.assets_published}
    org.assets_published = body.published
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "asset.sharing_changed",
        org,
        organization_id=org.id,
        before=before,
        after={"assets_published": body.published},
    )
    return SharingOut(organization_id=org.id, published=org.assets_published)


@router.get(
    "/reports/warranty",
    response_model=WarrantyReportOut,
    responses=ERR,
    summary="Warranty report across clients (expired and expiring first)",
)
def warranty(
    organization_id: int | None = None,
    status: str | None = None,
    within_days: int | None = Query(None, ge=0, le=3650),
    ctx: Ctx = require(P.REPORT_READ),
):
    return svc.warranty_report(ctx, organization_id, status, within_days)


@router.get(
    "/reports/warranty.csv",
    responses=ERR,
    summary="Warranty report as CSV",
)
def warranty_csv(
    organization_id: int | None = None,
    status: str | None = None,
    within_days: int | None = Query(None, ge=0, le=3650),
    ctx: Ctx = require(P.REPORT_READ),
):
    report = svc.warranty_report(ctx, organization_id, status, within_days)
    audit.record(
        ctx.db,
        ctx.user,
        "report.export",
        detail={
            "report": "warranty",
            "rows": report["total"],
            "params": {
                "organization_id": str(organization_id),
                "status": str(status),
                "within_days": str(within_days),
            },
        },
    )
    return Response(
        svc.warranty_csv(report),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="warranty-{report["as_of"]}.csv"'},
    )
