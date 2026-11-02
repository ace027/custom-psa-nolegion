"""Hudu articles related to a ticket, found by searching Hudu with the ticket subject.

Read-only toward Hudu and never stored. Results are cached in memory per (ticket, query) for a
few minutes so reopening a ticket does not call Hudu again. Failures are not cached.
"""

import logging
import re
import time
from dataclasses import asdict

from sqlalchemy import select

from app.asset_sync import safe_error
from app.integrations import registry
from app.models import Integration, IntegrationClientMap, Ticket
from app.schemas import HuduArticleOut, HuduArticlesOut

log = logging.getLogger("psa.hudu")

CACHE_SECONDS = 300
CACHE_MAX = 500
QUERY_MAX = 100
STOP_WORDS = frozenset(
    "a an and are as at be but by can cannot do does for from has have how i in is it its me my "
    "no not of on or our please re fw fwd so that the their there this to up us was we when "
    "where why will with you your".split()
)
_cache: dict[tuple[int, str], tuple[float, HuduArticlesOut]] = {}


def query_for(subject: str) -> str:
    words = [w for w in re.findall(r"[\w.+#-]+", subject) if w.lower() not in STOP_WORDS]
    return " ".join(words)[:QUERY_MAX].strip()


def _cached(key: tuple[int, str]) -> HuduArticlesOut | None:
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    return None


def _remember(key: tuple[int, str], value: HuduArticlesOut) -> None:
    now = time.monotonic()
    if len(_cache) >= CACHE_MAX:
        for k, (at, _) in list(_cache.items()):
            if now - at >= CACHE_SECONDS:
                _cache.pop(k, None)
        while len(_cache) >= CACHE_MAX:  # all fresh: drop the oldest
            _cache.pop(next(iter(_cache)), None)
    _cache[key] = (now, value)


def articles_for(db, ticket: Ticket) -> HuduArticlesOut:
    """`ticket` must come from an RLS-scoped lookup; the cache is only reached after it."""
    integration = db.scalars(
        select(Integration)
        .where(
            Integration.kind == "hudu",
            Integration.enabled.is_(True),
            Integration.credentials.is_not(None),
        )
        .order_by(Integration.id)
    ).first()
    if integration is None:
        return HuduArticlesOut(configured=False, articles=[])
    query = query_for(ticket.subject)
    if not query:
        return HuduArticlesOut(configured=True, articles=[])
    key = (ticket.id, query)
    if (hit := _cached(key)) is not None:
        return hit
    company = db.scalars(
        select(IntegrationClientMap.external_id).where(
            IntegrationClientMap.integration_id == integration.id,
            IntegrationClientMap.psa_organization_id == ticket.organization_id,
            IntegrationClientMap.ignored.is_(False),
        )
    ).first()
    try:
        found = registry.build_adapter(integration).search_articles(query, company)
    except Exception as exc:  # noqa: BLE001 - any Hudu or key failure is shown, never raised
        error = safe_error(exc)
        log.warning("Hudu article search for ticket %s failed: %s", ticket.id, error)
        return HuduArticlesOut(configured=True, articles=[], error=error)
    out = HuduArticlesOut(configured=True, articles=[HuduArticleOut(**asdict(a)) for a in found])
    _remember(key, out)
    return out
