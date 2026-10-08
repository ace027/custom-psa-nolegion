"""Settings > Integrations: connect a vendor, store its credentials (write-only), test it, and map
its clients to PSA clients. Credentials are never returned or logged."""

from sqlalchemy import select

from app import asset_sync as sync
from app import audit, crypto
from app.deps import Ctx
from app.errors import Conflict, NotFound
from app.integrations import registry
from app.integrations.base import VendorError
from app.integrations.hudu import validate_config as validate_hudu
from app.models import Integration, IntegrationClientMap, Organization, SyncRun


def _get(ctx: Ctx, integration_id: int) -> Integration:
    i = ctx.db.get(Integration, integration_id)
    if i is None:
        raise NotFound("Integration not found")
    return i


def view(i: Integration) -> dict:
    return {
        "id": i.id,
        "kind": i.kind,
        "name": i.name,
        "base_url": i.base_url,
        "config": i.config,
        "credentials_set": bool(i.credentials),
        "credentials_set_at": i.credentials_set_at,
        "enabled": i.enabled,
        "status": i.status,
        "last_error": i.last_error,
        "last_sync_at": i.last_sync_at,
        "sync_requested": i.sync_requested_at is not None,
    }


def _validate(kind: str, config: dict, creds: dict | None, required: bool) -> None:
    if kind == "hudu":
        try:
            validate_hudu(config)
        except ValueError as exc:
            raise Conflict(str(exc)) from exc
    if creds is not None or required:
        need = registry.CREDENTIAL_FIELDS[kind]
        missing = [f for f in need if not (creds or {}).get(f, "").strip()]
        if missing:
            raise Conflict(f"Credentials need: {', '.join(need)}")


def _store(i: Integration, creds: dict) -> None:
    keep = {f: creds[f].strip() for f in registry.CREDENTIAL_FIELDS[i.kind]}
    try:
        i.credentials = crypto.encrypt_credentials(keep)
    except crypto.CredentialsKeyError as exc:
        raise Conflict(str(exc)) from exc
    i.credentials_set_at = sync.now()


def list_integrations(ctx: Ctx) -> list[dict]:
    return [view(i) for i in ctx.db.scalars(select(Integration).order_by(Integration.id))]


def create(ctx: Ctx, data: dict) -> dict:
    _validate(data["kind"], data.get("config") or {}, data["credentials"], required=True)
    i = Integration(
        kind=data["kind"],
        name=data["name"].strip(),
        base_url=data["base_url"].strip().rstrip("/"),
        config=data.get("config") or {},
    )
    _store(i, data["credentials"])
    ctx.db.add(i)
    ctx.db.flush()
    audit.record(ctx.db, ctx.user, "integration.created", i, after=audit.snapshot(i))
    return view(i)


def update(ctx: Ctx, integration_id: int, data: dict) -> dict:
    i = _get(ctx, integration_id)
    before = audit.snapshot(i)
    creds = data.pop("credentials", None)
    if "config" in data:
        _validate(i.kind, data["config"], None, required=False)
    for key in ("name", "base_url", "config", "enabled"):
        if key in data:
            v = data[key]
            setattr(i, key, v.strip().rstrip("/") if key == "base_url" else v)
    if creds is not None:
        _validate(i.kind, i.config, creds, required=True)
        _store(i, creds)
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "integration.credentials_changed" if creds is not None else "integration.updated",
        i,
        before=before,
        after=audit.snapshot(i),
    )
    return view(i)


def test(ctx: Ctx, integration_id: int) -> dict:
    i = _get(ctx, integration_id)
    try:
        registry.build_adapter(i).test_connection()
    except VendorError as exc:
        i.status, i.last_error = "error", str(exc)
        result = {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        i.status, i.last_error = "error", type(exc).__name__
        result = {"ok": False, "error": type(exc).__name__}
    else:
        i.status, i.last_error = "ok", None
        result = {"ok": True, "error": None}
    audit.record(ctx.db, ctx.user, "integration.tested", i, detail={"ok": result["ok"]})
    return result


def request_sync(ctx: Ctx, integration_id: int) -> dict:
    i = _get(ctx, integration_id)
    if not i.enabled:
        raise Conflict("This integration is turned off")
    i.sync_requested_at = sync.now()
    audit.record(ctx.db, ctx.user, "integration.sync_requested", i)
    return view(i)


def runs(ctx: Ctx, integration_id: int, limit: int = 20) -> list[SyncRun]:
    _get(ctx, integration_id)
    return list(
        ctx.db.scalars(
            select(SyncRun)
            .where(SyncRun.integration_id == integration_id)
            .order_by(SyncRun.id.desc())
            .limit(limit)
        )
    )


# ---- client mapping ----
def _suggestions(ctx: Ctx) -> dict[str, int]:
    return {o.name.strip().lower(): o.id for o in ctx.db.scalars(select(Organization))}


def clients(ctx: Ctx, integration_id: int) -> list[dict]:
    _get(ctx, integration_id)
    names = _suggestions(ctx)
    out = []
    for m in ctx.db.scalars(
        select(IntegrationClientMap)
        .where(IntegrationClientMap.integration_id == integration_id)
        .order_by(IntegrationClientMap.external_name)
    ):
        unmapped = m.psa_organization_id is None and not m.ignored
        out.append(
            {
                "id": m.id,
                "external_id": m.external_id,
                "external_name": m.external_name,
                "organization_id": m.psa_organization_id,
                "ignored": m.ignored,
                "needs_mapping": unmapped,
                "suggested_organization_id": names.get(m.external_name.strip().lower())
                if unmapped
                else None,
                "first_seen_at": m.first_seen_at,
            }
        )
    return out


def refresh_clients(ctx: Ctx, integration_id: int) -> list[dict]:
    i = _get(ctx, integration_id)
    try:
        sync.refresh_clients(ctx, i, registry.build_adapter(i))
    except VendorError as exc:
        raise Conflict(str(exc)) from exc
    return clients(ctx, integration_id)


def map_client(
    ctx: Ctx, integration_id: int, map_id: int, organization_id: int | None, ignored: bool
) -> dict:
    _get(ctx, integration_id)
    m = ctx.db.get(IntegrationClientMap, map_id)
    if m is None or m.integration_id != integration_id:
        raise NotFound("Vendor client not found")
    if ignored and organization_id is not None:
        raise Conflict("A vendor client is either mapped or ignored, not both")
    if organization_id is not None and ctx.db.get(Organization, organization_id) is None:
        raise NotFound("Organization not found")
    before = {"organization_id": m.psa_organization_id, "ignored": m.ignored}
    m.psa_organization_id, m.ignored = organization_id, ignored
    ctx.db.flush()
    audit.record(
        ctx.db,
        ctx.user,
        "integration.client_mapped",
        m,
        organization_id=organization_id,
        before=before,
        after={"organization_id": organization_id, "ignored": ignored},
        detail={"integration_id": integration_id, "external_name": m.external_name},
    )
    return next(c for c in clients(ctx, integration_id) if c["id"] == m.id)
