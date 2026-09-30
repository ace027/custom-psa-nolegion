import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.context import client_ip_var, request_id_var
from app.errors import Conflict, Forbidden, NotFound
from app.routers import auth, billing, config, health, invoices, organizations, tickets, users

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="PSA API",
        version="0.1.0",
        description="Custom PSA for a small MSP. Interactive docs at /api/docs.",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request_id_var.set(rid[:64])
        client_ip_var.set(request.client.host if request.client else None)
        # CSRF defense in depth on top of SameSite=Lax: a cross-site form/fetch cannot add this
        # header without a CORS preflight, which we never allow.
        if request.method in UNSAFE and request.headers.get("x-requested-with") != "psa":
            return JSONResponse({"detail": "Missing X-Requested-With header"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    # Only holds the short-lived OIDC state/nonce during the login redirect.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="psa_oidc_state",
        max_age=600,
        same_site="lax",
        https_only=settings.is_production,
    )

    @app.exception_handler(NotFound)
    async def _nf(_: Request, exc: NotFound):
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(Conflict)
    async def _cf(_: Request, exc: Conflict):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(Forbidden)
    async def _fb(_: Request, exc: Forbidden):
        return JSONResponse({"detail": str(exc)}, status_code=403)

    app.include_router(health.router)
    for r in (
        auth.router,
        organizations.router,
        users.router,
        tickets.router,
        config.router,
        billing.router,
        invoices.router,
    ):
        app.include_router(r, prefix="/api")
    return app


app = create_app()
