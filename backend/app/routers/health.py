from fastapi import APIRouter
from sqlalchemy import text

from app import db as dbmod

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe")
def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness probe (checks the database)")
def readyz() -> dict:
    with dbmod.new_session() as s:
        s.execute(text("SELECT 1"))
    return {"status": "ready"}
