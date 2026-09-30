import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Session as LoginSession
from app.models import User


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User, ip: str | None, user_agent: str | None) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        LoginSession(
            token_hash=_hash(token),
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=get_settings().session_max_age_hours),
            ip=ip,
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    return token


def get_user_for_token(db: Session, token: str | None) -> User | None:
    """Returns the active user for a valid, unexpired session token, else None."""
    if not token:
        return None
    row = db.execute(
        select(User)
        .join(LoginSession, LoginSession.user_id == User.id)
        .where(
            LoginSession.token_hash == _hash(token),
            LoginSession.expires_at > datetime.now(UTC),
            User.is_active.is_(True),
        )
    ).scalar_one_or_none()
    return row


def delete_session(db: Session, token: str) -> None:
    db.execute(delete(LoginSession).where(LoginSession.token_hash == _hash(token)))


def revoke_user_sessions(db: Session, user_id: int) -> int:
    result = db.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
    return result.rowcount or 0
