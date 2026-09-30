from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app import audit, services
from app import db as dbmod
from app import permissions as P
from app import repositories as repo
from app.auth import oidc, sessions
from app.config import get_settings
from app.deps import Ctx, authenticated
from app.schemas import DevLoginIn, ErrorOut, MeOut

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        s.session_cookie_name,
        token,
        max_age=s.session_max_age_hours * 3600,
        httponly=True,
        secure=s.is_production,
        samesite="lax",
        path="/",
    )


def _client(request: Request) -> tuple[str | None, str | None]:
    return (request.client.host if request.client else None), request.headers.get("user-agent")


@router.get(
    "/login",
    summary="Start Entra ID sign-in (redirects to Microsoft)",
    responses={503: {"model": ErrorOut}},
)
async def login(request: Request):
    s = get_settings()
    if not s.entra_configured:
        raise HTTPException(503, "Entra ID sign-in is not configured")
    redirect_uri = f"{s.public_url}/api/auth/callback"
    return await oidc.get_oauth().entra.authorize_redirect(request, redirect_uri)


@router.get(
    "/callback",
    summary="Entra ID redirect target; creates the session",
    responses={403: {"model": ErrorOut}, 503: {"model": ErrorOut}},
)
async def callback(request: Request):
    s = get_settings()
    if not s.entra_configured:
        raise HTTPException(503, "Entra ID sign-in is not configured")
    try:
        token = await oidc.get_oauth().entra.authorize_access_token(request)
        claims = dict(token.get("userinfo") or {})
    except Exception:
        audit.record_auth_event("auth.login_failed", detail={"reason": "token_exchange"})
        raise HTTPException(403, "Sign-in failed") from None

    ip, ua = _client(request)
    with dbmod.new_session() as db:
        try:
            user = oidc.resolve_user_from_claims(db, claims)
        except oidc.LoginDenied as denied:
            db.rollback()
            audit.record_auth_event(
                "auth.login_failed",
                detail={
                    "reason": denied.reason,
                    "email": claims.get("email") or claims.get("preferred_username"),
                },
            )
            raise HTTPException(403, "Your account is not authorized") from None
        services.touch_login(db, user)
        cookie = sessions.create_session(db, user, ip, ua)
        db.commit()
        user_id = user.id
    audit.record_auth_event("auth.login", user_id=user_id)
    response = RedirectResponse(f"{s.public_url}/", status_code=303)
    _set_cookie(response, cookie)
    return response


@router.post(
    "/dev-login",
    response_model=MeOut,
    summary="DEV ONLY: sign in as an existing user",
    responses={404: {"model": ErrorOut}, 403: {"model": ErrorOut}},
)
def dev_login(body: DevLoginIn, request: Request, response: Response):
    s = get_settings()
    if not s.dev_login_enabled or s.is_production:
        raise HTTPException(404, "Not found")  # indistinguishable from a missing route
    ip, ua = _client(request)
    with dbmod.new_session() as db:
        user = repo.get_user_by_email(db, body.email)
        if user is None or not user.is_active:
            db.rollback()
            audit.record_auth_event(
                "auth.login_failed", detail={"reason": "dev_login_unknown", "email": body.email}
            )
            raise HTTPException(403, "Unknown or inactive user")
        services.touch_login(db, user)
        cookie = sessions.create_session(db, user, ip, ua)
        db.commit()
        out = MeOut(
            **{
                **{
                    c: getattr(user, c)
                    for c in ("id", "email", "display_name", "role", "is_active", "last_login_at")
                },
                "permissions": sorted(P.MATRIX[user.role]),
            }
        )
    audit.record_auth_event("auth.login", user_id=out.id, detail={"method": "dev"})
    _set_cookie(response, cookie)
    return out


@router.post("/logout", status_code=204, summary="End the current session")
def logout(request: Request, response: Response, ctx: Ctx = authenticated()):
    token = request.cookies.get(get_settings().session_cookie_name)
    if token:
        sessions.delete_session(ctx.db, token)
    audit.record(ctx.db, ctx.user, "auth.logout", ctx.user)
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut, summary="The signed-in user and their permissions")
def me(ctx: Ctx = authenticated()):
    u = ctx.user
    return MeOut(
        id=u.id,
        email=u.email,
        display_name=u.display_name,
        role=u.role,
        is_active=u.is_active,
        last_login_at=u.last_login_at,
        permissions=sorted(P.MATRIX[u.role]),
    )
