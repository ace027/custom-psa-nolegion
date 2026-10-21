"""Automation rules: admins define, test and review if-this-then-that rules on ticket and
monitoring-alert events."""

from fastapi import APIRouter, Query

from app import automation as svc
from app import permissions as P
from app.deps import Ctx, require
from app.errors import Conflict
from app.schemas import (
    ErrorOut,
    RuleIn,
    RuleOut,
    RulePatch,
    RuleRunOut,
    RuleTest,
    RuleTestOut,
)

router = APIRouter(prefix="/automation", tags=["automation"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}
M = P.AUTOMATION_MANAGE


@router.get("/rules", response_model=list[RuleOut], summary="List automation rules")
def list_rules(include_archived: bool = False, ctx: Ctx = require(M)):
    return svc.list_rules(ctx, include_archived)


@router.post(
    "/rules",
    response_model=RuleOut,
    status_code=201,
    responses=ERR,
    summary="Create an automation rule",
)
def create(body: RuleIn, ctx: Ctx = require(M)):
    return svc.create(ctx, body.model_dump())


@router.post(
    "/rules/test",
    response_model=RuleTestOut,
    responses=ERR,
    summary="Dry run: test a saved or unsaved rule against a ticket without changing anything",
)
def test(body: RuleTest, ctx: Ctx = require(M)):
    if (body.rule_id is None) == (body.rule is None):
        raise Conflict("Give either rule_id or rule, not both")
    return svc.dry_run(
        ctx, body.rule_id, body.rule.model_dump() if body.rule else None, body.ticket_id
    )


@router.patch(
    "/rules/{rule_id}",
    response_model=RuleOut,
    responses=ERR,
    summary="Edit an automation rule",
)
def update(rule_id: int, body: RulePatch, ctx: Ctx = require(M)):
    return svc.update(ctx, rule_id, body.model_dump(exclude_unset=True))


@router.post(
    "/rules/{rule_id}/archive",
    response_model=RuleOut,
    responses=ERR,
    summary="Archive an automation rule (it stops running and is hidden)",
)
def archive(rule_id: int, ctx: Ctx = require(M)):
    return svc.archive(ctx, rule_id)


@router.get(
    "/rules/{rule_id}/runs",
    response_model=list[RuleRunOut],
    responses=ERR,
    summary="Run history of a rule with its per-run trace, newest first",
)
def runs(rule_id: int, limit: int = Query(50, ge=1, le=200), ctx: Ctx = require(M)):
    return svc.runs(ctx, rule_id, limit)
