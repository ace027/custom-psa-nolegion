"""Late fees: preview what qualifies, apply the ones a person approves."""

from fastapi import APIRouter

from app import late_fees as svc
from app import permissions as P
from app.deps import Ctx, require
from app.schemas import (
    ErrorOut,
    LateFeeAppliedOut,
    LateFeeApplyIn,
    LateFeePreviewOut,
    LateFeeRow,
)

router = APIRouter(tags=["late-fees"])
ERR = {409: {"model": ErrorOut}}


@router.get(
    "/late-fees/preview",
    response_model=LateFeePreviewOut,
    summary="Invoices that qualify for a late fee under the Settings rule (changes nothing)",
)
def preview(organization_id: int | None = None, ctx: Ctx = require(P.BILLING_READ)):
    rule, configured, rows = svc.candidates(ctx, organization_id)
    return LateFeePreviewOut(configured=configured, **rule, rows=[LateFeeRow(**r) for r in rows])


@router.post(
    "/late-fees/apply",
    response_model=list[LateFeeAppliedOut],
    status_code=201,
    responses=ERR,
    summary="Charge the late fee on the chosen invoices (billed on the client's next invoice)",
)
def apply(body: LateFeeApplyIn, ctx: Ctx = require(P.BILLING_FINALIZE)):
    return svc.apply(ctx, body.invoice_ids)


@router.get(
    "/late-fees/applied",
    response_model=list[LateFeeAppliedOut],
    summary="Late fees already applied, newest first",
)
def applied(organization_id: int | None = None, ctx: Ctx = require(P.BILLING_READ)):
    return svc.applied(ctx, organization_id)
