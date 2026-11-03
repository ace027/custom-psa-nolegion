"""Create (or restore) the first admin from BOOTSTRAP_ADMIN_EMAIL. Run by the migrate job:

    python -m app.bootstrap_admin

Idempotent: an empty variable is a no-op; an existing user with that email is made an active admin;
otherwise a user is inserted. No entra_oid is set: the existing staff sign-in matches the row by
email on first login and binds the Entra object id then (see auth/oidc.resolve_user_from_claims).
Uses the owner (migration) connection like the migrate step, because no session exists yet.
"""

import os
import re
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app import audit
from app import repositories as repo
from app.config import get_settings
from app.models import User

EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def run(email: str | None = None) -> str:
    """Returns what happened: 'skipped', 'created', 'promoted' or 'unchanged'."""
    email = (os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "") if email is None else email).strip()
    if not email or email == "unset":
        return "skipped"
    if len(email) > 320 or not EMAIL_RE.fullmatch(email):
        raise SystemExit("BOOTSTRAP_ADMIN_EMAIL is not a valid email address")
    engine = create_engine(get_settings().migration_database_url)
    try:
        with Session(engine) as db:
            db.execute(text("SELECT set_config('app.org_scope', 'all', true)"))
            user = repo.get_user_by_email(db, email)
            if user is None:
                user = User(email=email, display_name=email.split("@")[0], role="admin")
                db.add(user)
                db.flush()
                outcome = "created"
                before = None
            elif user.role != "admin" or not user.is_active:
                before = audit.snapshot(user)
                user.role, user.is_active = "admin", True
                db.flush()
                outcome = "promoted"
            else:
                return "unchanged"
            audit.record(
                db,
                None,
                "auth.bootstrap_admin",
                user,
                before=before,
                after=audit.snapshot(user),
                detail={"outcome": outcome},
            )
            db.commit()
            return outcome
    finally:
        engine.dispose()


if __name__ == "__main__":
    print(f"bootstrap admin: {run()}", file=sys.stderr)
