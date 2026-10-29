"""Role dashboards. The manager dashboard lives in routers/reports.py (report:read)."""

from fastapi import APIRouter

from app import dashboards as svc
from app import permissions as P
from app.deps import Ctx, require
from app.report_schemas import MyDashboardOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "/me",
    response_model=MyDashboardOut,
    summary="My open tickets, SLA risk, appointments today and this week's time (own data only)",
)
def my_dashboard(ctx: Ctx = require(P.TICKET_READ)):
    return svc.me(ctx)
