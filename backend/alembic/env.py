from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings
from app.models import Base

target_metadata = Base.metadata


def run_migrations() -> None:
    # Migrations run as the table OWNER (MIGRATION_DATABASE_URL); the app itself never does.
    url = context.get_x_argument(as_dictionary=True).get("url") or (
        get_settings().migration_database_url
    )
    engine = create_engine(url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
