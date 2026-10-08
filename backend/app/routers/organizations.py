from fastapi import APIRouter, HTTPException, Query

from app import permissions as P
from app import repositories as repo
from app import services
from app.deps import Ctx, require
from app.schemas import (
    ContactIn,
    ContactOut,
    ContactPatch,
    ErrorOut,
    OrganizationIn,
    OrganizationOut,
    OrganizationPatch,
    Page,
    SiteIn,
    SiteOut,
    SitePatch,
)

router = APIRouter(tags=["organizations"])
ERR = {404: {"model": ErrorOut}, 409: {"model": ErrorOut}}


def _org_or_404(ctx: Ctx, org_id: int):
    org = repo.get_organization(ctx.db, ctx.scope, org_id)
    if org is None:
        raise HTTPException(404, "Organization not found")
    return org


# ---- organizations ----
@router.get("/organizations", response_model=Page[OrganizationOut], summary="List organizations")
def list_organizations(
    q: str | None = Query(None, description="Case-insensitive name search"),
    include_archived: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: Ctx = require(P.ORG_READ),
):
    items, total = repo.list_organizations(
        ctx.db, ctx.scope, q=q, include_archived=include_archived, limit=limit, offset=offset
    )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/organizations",
    response_model=OrganizationOut,
    status_code=201,
    responses=ERR,
    summary="Create an organization",
)
def create_organization(body: OrganizationIn, ctx: Ctx = require(P.ORG_WRITE)):
    return services.create_organization(ctx, body.model_dump())


@router.get(
    "/organizations/{org_id}",
    response_model=OrganizationOut,
    responses=ERR,
    summary="Get an organization",
)
def get_organization(org_id: int, ctx: Ctx = require(P.ORG_READ)):
    return _org_or_404(ctx, org_id)


@router.patch(
    "/organizations/{org_id}",
    response_model=OrganizationOut,
    responses=ERR,
    summary="Update an organization",
)
def update_organization(org_id: int, body: OrganizationPatch, ctx: Ctx = require(P.ORG_WRITE)):
    return services.update_organization(ctx, org_id, body.model_dump(exclude_unset=True))


@router.post(
    "/organizations/{org_id}/archive",
    response_model=OrganizationOut,
    responses=ERR,
    summary="Archive an organization (soft delete)",
)
def archive_organization(org_id: int, ctx: Ctx = require(P.ORG_WRITE)):
    return services.set_organization_archived(ctx, org_id, True)


@router.post(
    "/organizations/{org_id}/unarchive",
    response_model=OrganizationOut,
    responses=ERR,
    summary="Restore an archived organization",
)
def unarchive_organization(org_id: int, ctx: Ctx = require(P.ORG_WRITE)):
    return services.set_organization_archived(ctx, org_id, False)


# ---- sites ----
@router.get(
    "/organizations/{org_id}/sites",
    response_model=list[SiteOut],
    responses=ERR,
    summary="List an organization's sites",
)
def list_sites(org_id: int, include_archived: bool = False, ctx: Ctx = require(P.ORG_READ)):
    _org_or_404(ctx, org_id)
    return repo.list_sites(ctx.db, ctx.scope, org_id, include_archived)


@router.post(
    "/organizations/{org_id}/sites",
    response_model=SiteOut,
    status_code=201,
    responses=ERR,
    summary="Create a site",
)
def create_site(org_id: int, body: SiteIn, ctx: Ctx = require(P.ORG_WRITE)):
    return services.create_site(ctx, org_id, body.model_dump())


@router.patch("/sites/{site_id}", response_model=SiteOut, responses=ERR, summary="Update a site")
def update_site(site_id: int, body: SitePatch, ctx: Ctx = require(P.ORG_WRITE)):
    return services.update_site(ctx, site_id, body.model_dump(exclude_unset=True))


@router.post(
    "/sites/{site_id}/archive", response_model=SiteOut, responses=ERR, summary="Archive a site"
)
def archive_site(site_id: int, ctx: Ctx = require(P.ORG_WRITE)):
    return services.set_site_archived(ctx, site_id, True)


@router.post(
    "/sites/{site_id}/unarchive",
    response_model=SiteOut,
    responses=ERR,
    summary="Restore an archived site",
)
def unarchive_site(site_id: int, ctx: Ctx = require(P.ORG_WRITE)):
    return services.set_site_archived(ctx, site_id, False)


# ---- contacts ----
def _portal_grant_needs_permission(ctx: Ctx, data: dict) -> None:
    """Giving someone client-portal access exposes a client's data, so it is an admin decision.
    Turning access off (or leaving it alone) needs only the normal contact permission."""
    if (
        data.get("portal_access") or data.get("portal_org_tickets") or data.get("portal_assets")
    ) and not P.has_permission(ctx.user.role, P.PORTAL_MANAGE):
        raise HTTPException(status_code=403, detail="Only an admin can grant client portal access")


@router.get(
    "/organizations/{org_id}/contacts",
    response_model=list[ContactOut],
    responses=ERR,
    summary="List an organization's contacts",
)
def list_contacts(org_id: int, include_archived: bool = False, ctx: Ctx = require(P.ORG_READ)):
    _org_or_404(ctx, org_id)
    return repo.list_contacts(ctx.db, ctx.scope, org_id, include_archived)


@router.post(
    "/organizations/{org_id}/contacts",
    response_model=ContactOut,
    status_code=201,
    responses=ERR,
    summary="Create a contact",
)
def create_contact(org_id: int, body: ContactIn, ctx: Ctx = require(P.ORG_WRITE)):
    _portal_grant_needs_permission(ctx, body.model_dump())
    return services.create_contact(ctx, org_id, body.model_dump())


@router.patch(
    "/contacts/{contact_id}", response_model=ContactOut, responses=ERR, summary="Update a contact"
)
def update_contact(contact_id: int, body: ContactPatch, ctx: Ctx = require(P.ORG_WRITE)):
    data = body.model_dump(exclude_unset=True)
    _portal_grant_needs_permission(ctx, data)
    return services.update_contact(ctx, contact_id, data)


@router.post(
    "/contacts/{contact_id}/archive",
    response_model=ContactOut,
    responses=ERR,
    summary="Archive a contact",
)
def archive_contact(contact_id: int, ctx: Ctx = require(P.ORG_WRITE)):
    return services.set_contact_archived(ctx, contact_id, True)


@router.post(
    "/contacts/{contact_id}/unarchive",
    response_model=ContactOut,
    responses=ERR,
    summary="Restore an archived contact",
)
def unarchive_contact(contact_id: int, ctx: Ctx = require(P.ORG_WRITE)):
    return services.set_contact_archived(ctx, contact_id, False)
