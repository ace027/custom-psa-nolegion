"""Customer satisfaction: the public answer endpoint and staff views."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import csat as svc
from app import permissions as P
from app.deps import Ctx, require
from app.errors import NotFound
from app.portal_deps import public_session
from app.schemas import CsatOut, CsatRespondIn, CsatRespondOut, CsatSummaryOut, ErrorOut

router = APIRouter(tags=["satisfaction"])


@router.post(
    "/csat/respond",
    response_model=CsatRespondOut,
    responses={404: {"model": ErrorOut}},
    summary="Answer a satisfaction survey from its emailed link (public, single use)",
)
def respond(body: CsatRespondIn, db: Session = Depends(public_session)):
    try:
        number = svc.respond(db, body.token, body.rating, body.comment)
    except NotFound as exc:
        raise HTTPException(404, "This link has expired or was already used") from exc
    return CsatRespondOut(ticket_number=number)


@router.get(
    "/csat/summary",
    response_model=CsatSummaryOut,
    summary="Satisfaction ratings received over the last N days",
)
def summary(days: int = Query(90, ge=1, le=730), ctx: Ctx = require(P.TICKET_READ)):
    return svc.summary(ctx, days)


@router.get(
    "/tickets/{ticket_id}/csat",
    response_model=CsatOut | None,
    responses={404: {"model": ErrorOut}},
    summary="The satisfaction survey sent for this ticket, and the answer if any",
)
def ticket_csat(ticket_id: int, ctx: Ctx = require(P.TICKET_READ)):
    s = svc.for_ticket(ctx, ticket_id)
    if s is None:
        return None
    return CsatOut(
        sent_to=s.sent_to,
        requested_at=s.created_at,
        rating=s.rating,
        comment=s.comment,
        responded_at=s.responded_at,
    )
