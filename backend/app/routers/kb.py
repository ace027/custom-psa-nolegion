"""Knowledge base: staff articles and ticket suggestions."""

from fastapi import APIRouter, Query

from app import kb as svc
from app import permissions as P
from app.deps import Ctx, require
from app.kb_schemas import (
    KbArticleIn,
    KbArticleOut,
    KbArticlePatch,
    KbArticleSummary,
    KbStatus,
    Visibility,
)
from app.schemas import ErrorOut, Page

router = APIRouter(prefix="/kb", tags=["knowledge base"])
ERR = {404: {"model": ErrorOut}}
NOT_NULL = ("title", "body", "visibility", "status", "tags")


@router.get(
    "/articles",
    response_model=Page[KbArticleSummary],
    summary="Search and list knowledge-base articles",
)
def list_articles(
    q: str | None = Query(default=None, min_length=2, max_length=100),
    status: KbStatus | None = None,
    visibility: Visibility | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ctx: Ctx = require(P.KB_READ),
):
    items, total = svc.list_articles(ctx, q, status, visibility, limit, offset)
    return Page[KbArticleSummary](
        items=[svc.summary(a) for a in items], total=total, limit=limit, offset=offset
    )


@router.get(
    "/articles/{article_id}",
    response_model=KbArticleOut,
    responses=ERR,
    summary="One knowledge-base article",
)
def get_article(article_id: int, ctx: Ctx = require(P.KB_READ)):
    return svc.article_out(ctx, svc.get_article(ctx, article_id))


@router.post(
    "/articles",
    response_model=KbArticleOut,
    status_code=201,
    summary="Write a knowledge-base article",
)
def create_article(body: KbArticleIn, ctx: Ctx = require(P.KB_WRITE)):
    return svc.article_out(ctx, svc.create_article(ctx, body.model_dump()))


@router.patch(
    "/articles/{article_id}",
    response_model=KbArticleOut,
    responses=ERR,
    summary="Edit, publish or archive a knowledge-base article",
)
def update_article(article_id: int, body: KbArticlePatch, ctx: Ctx = require(P.KB_WRITE)):
    data = {
        k: v
        for k, v in body.model_dump(exclude_unset=True).items()
        if v is not None or k not in NOT_NULL
    }
    return svc.article_out(ctx, svc.update_article(ctx, article_id, data))


@router.get(
    "/suggestions",
    response_model=list[KbArticleSummary],
    responses=ERR,
    summary="Published articles that may help with a ticket (up to 5)",
)
def suggestions(ticket_id: int, ctx: Ctx = require(P.KB_READ)):
    return [svc.summary(a) for a in svc.suggestions_for_ticket(ctx, ticket_id)]
