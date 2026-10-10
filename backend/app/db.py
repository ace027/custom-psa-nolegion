from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def new_session() -> Session:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)()


def set_org_scope(db: Session, scope: str) -> None:
    """Tell Postgres row-level security which orgs this transaction may see.

    `true` makes the setting transaction-local (SET LOCAL), so it can never leak to another
    request that reuses the pooled connection.
    """
    db.execute(text("SELECT set_config('app.org_scope', :s, true)"), {"s": scope})
