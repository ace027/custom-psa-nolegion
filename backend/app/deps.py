"""Request plumbing: authenticate, authorize, open a scoped transaction.

Every route declares its permission through `require(...)` (or `authenticated()`); a test
verifies that no route is missing one.
"""

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import audit
from app import db as dbmod
from app.auth import sessions
from app.config import get_settings
from app.models import User
from app.permissions import has_permission
from app.scope import Scope


@dataclass
class Ctx:
    db: Session
    user: User | None  # None = system actor (mail worker)
    scope: Scope


def _make_dependency(permission: str | None):
    def dependency(request: Request) -> Iterator[Ctx]:
        db = dbmod.new_session()
        try:
            token = request.cookies.get(get_settings().session_cookie_name)
            user = sessions.get_user_for_token(db, token)
            if user is None:
                raise HTTPException(status_code=401, detail="Not authenticated")
            if permission and not has_permission(user.role, permission):
                audit.record_auth_event(
                    "auth.denied",
                    user_id=user.id,
                    detail={
                        "permission": permission,
                        "path": request.url.path,
                        "method": request.method,
                    },
                )
                raise HTTPException(status_code=403, detail="Not permitted")
            scope = Scope.all()  # staff see every client; portal principals will be narrower
            dbmod.set_org_scope(db, scope.rls_value())
            yield Ctx(db=db, user=user, scope=scope)
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    dependency.__psa_permission__ = permission or "authenticated"  # type: ignore[attr-defined]
    return dependency


def require(permission: str):
    # scope="function": commit happens BEFORE the response is sent, so a failed commit is a
    # real 500 and the client never sees success for a change that was rolled back.
    return Depends(_make_dependency(permission), scope="function")


def authenticated():
    return Depends(_make_dependency(None), scope="function")
