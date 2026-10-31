"""Knowledge base service. Articles are staff-internal content shared across clients (no RLS).
Search is Postgres full text: websearch_to_tsquery for what people type, and to_tsquery only
for terms reduced to [A-Za-z0-9] words, so user text can never cause a tsquery syntax error.
Articles are archived, never deleted."""

import re

from sqlalchemy import func, select

from app import audit
from app.deps import Ctx
from app.errors import NotFound
from app.kb_schemas import KbArticleOut, KbArticleSummary, snippet_of
from app.models import KbArticle, Ticket, User

SUGGESTION_LIMIT = 5
MAX_TERMS = 12
WORD = re.compile(r"[A-Za-z0-9]{3,}")
EDITABLE = ("title", "body", "visibility", "status", "tags")


def _snapshot(article: KbArticle) -> dict:
    snap = audit.snapshot(article)
    snap.pop("search", None)  # generated column, large and derived
    return snap


def _escape_like(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def summary(article: KbArticle) -> KbArticleSummary:
    return KbArticleSummary(
        id=article.id,
        title=article.title,
        visibility=article.visibility,
        status=article.status,
        tags=article.tags,
        updated_at=article.updated_at,
        snippet=snippet_of(article.body),
    )


def article_out(ctx: Ctx, article: KbArticle) -> KbArticleOut:
    ids = {i for i in (article.created_by_id, article.updated_by_id) if i is not None}
    names = (
        dict(ctx.db.execute(select(User.id, User.display_name).where(User.id.in_(ids))).all())
        if ids
        else {}
    )
    out = KbArticleOut.model_validate(article)
    out.created_by_name = names.get(article.created_by_id)
    out.updated_by_name = names.get(article.updated_by_id)
    return out


def _text_match(ctx: Ctx, stmt, q: str):
    """Narrow `stmt` to articles matching q and order by relevance. Falls back to a title
    substring match when the query has no searchable words (e.g. only stop words)."""
    tsq = func.websearch_to_tsquery("english", q)
    empty = ctx.db.execute(select(func.numnode(tsq))).scalar_one() == 0
    if empty:
        like = f"%{_escape_like(q)}%"
        return stmt.where(KbArticle.title.ilike(like, escape="\\")).order_by(
            KbArticle.updated_at.desc(), KbArticle.id.desc()
        )
    return stmt.where(KbArticle.search.op("@@")(tsq)).order_by(
        func.ts_rank(KbArticle.search, tsq).desc(),
        KbArticle.updated_at.desc(),
        KbArticle.id.desc(),
    )


def list_articles(
    ctx: Ctx,
    q: str | None,
    status: str | None,
    visibility: str | None,
    limit: int,
    offset: int,
) -> tuple[list[KbArticle], int]:
    stmt = select(KbArticle)
    if status:
        stmt = stmt.where(KbArticle.status == status)
    if visibility:
        stmt = stmt.where(KbArticle.visibility == visibility)
    total = ctx.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    if q and q.strip():
        stmt = _text_match(ctx, stmt, q.strip())
        total = ctx.db.execute(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        ).scalar_one()
    else:
        stmt = stmt.order_by(KbArticle.updated_at.desc(), KbArticle.id.desc())
    items = list(ctx.db.scalars(stmt.limit(limit).offset(offset)))
    return items, total


def get_article(ctx: Ctx, article_id: int) -> KbArticle:
    article = ctx.db.get(KbArticle, article_id)
    if article is None:
        raise NotFound("Article not found")
    return article


def create_article(ctx: Ctx, data: dict) -> KbArticle:
    uid = ctx.user.id if ctx.user else None
    article = KbArticle(**data, created_by_id=uid, updated_by_id=uid)
    ctx.db.add(article)
    ctx.db.flush()
    ctx.db.refresh(article)
    audit.record(ctx.db, ctx.user, "kb_article.create", article, after=_snapshot(article))
    return article


def update_article(ctx: Ctx, article_id: int, data: dict) -> KbArticle:
    article = get_article(ctx, article_id)
    before = _snapshot(article)
    for key in EDITABLE:
        if key in data:
            setattr(article, key, data[key])
    article.updated_by_id = ctx.user.id if ctx.user else None
    ctx.db.flush()
    ctx.db.refresh(article)
    audit.record(
        ctx.db, ctx.user, "kb_article.update", article, before=before, after=_snapshot(article)
    )
    return article


def _terms(*texts: str | None) -> list[str]:
    seen: dict[str, None] = {}
    for text in texts:
        for word in WORD.findall(text or ""):
            seen.setdefault(word.lower())
            if len(seen) >= MAX_TERMS:
                return list(seen)
    return list(seen)


def suggestions_for_ticket(ctx: Ctx, ticket_id: int) -> list[KbArticle]:
    ticket = ctx.db.scalars(
        ctx.scope.apply(select(Ticket).where(Ticket.id == ticket_id), Ticket.organization_id)
    ).first()
    if ticket is None:
        raise NotFound("Ticket not found")
    terms = _terms(ticket.subject, ticket.description)
    if not terms:
        return []
    tsq = func.to_tsquery("english", " | ".join(terms))
    stmt = (
        select(KbArticle)
        .where(KbArticle.status == "published", KbArticle.search.op("@@")(tsq))
        .order_by(func.ts_rank(KbArticle.search, tsq).desc(), KbArticle.id)
        .limit(SUGGESTION_LIMIT)
    )
    return list(ctx.db.scalars(stmt))


# ---- client portal: published AND client-facing only; anything else does not exist ----
def portal_list(ctx: Ctx, q: str | None, limit: int = 50) -> list[KbArticle]:
    stmt = select(KbArticle).where(
        KbArticle.status == "published", KbArticle.visibility == "client"
    )
    if q and q.strip():
        stmt = _text_match(ctx, stmt, q.strip())
    else:
        stmt = stmt.order_by(KbArticle.title, KbArticle.id)
    return list(ctx.db.scalars(stmt.limit(limit)))


def portal_get(ctx: Ctx, article_id: int) -> KbArticle:
    article = ctx.db.scalars(
        select(KbArticle).where(
            KbArticle.id == article_id,
            KbArticle.status == "published",
            KbArticle.visibility == "client",
        )
    ).first()
    if article is None:
        raise NotFound("Article not found")
    return article
