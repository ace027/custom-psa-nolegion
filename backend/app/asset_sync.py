"""Sync one vendor into the asset inventory. Read-only toward the vendor.

Guarantees (each covered by tests):
- Repeating a sync changes nothing.
- A failed or partial sync never deletes or blanks data. A client whose fetch failed is left alone.
- Assets are never deleted: ones the vendor stops reporting are marked retired after N days.
- Manual overrides live in their own table, so a sync cannot overwrite them.
- Unmapped vendor clients are never guessed; they are skipped and listed as a to-do.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from app import assets as asvc
from app import audit
from app.deps import Ctx
from app.integrations import registry
from app.integrations.base import RemoteAsset, VendorError
from app.models import (
    Asset,
    AssetSource,
    Integration,
    IntegrationClientMap,
    SyncRun,
)

log = logging.getLogger("psa.sync")
DEFAULT_RETIRE_DAYS = 30


def now() -> datetime:
    return datetime.now().astimezone()


def refresh_clients(ctx: Ctx, integration: Integration, adapter) -> list[IntegrationClientMap]:
    """Record the vendor's clients. New ones start unmapped; existing mappings are untouched."""
    remote = adapter.list_clients()
    maps = {
        m.external_id: m
        for m in ctx.db.scalars(
            select(IntegrationClientMap).where(
                IntegrationClientMap.integration_id == integration.id
            )
        )
    }
    stamp = now()
    for rc in remote:
        m = maps.get(rc.external_id)
        if m is None:
            m = IntegrationClientMap(
                integration_id=integration.id, external_id=rc.external_id, external_name=rc.name
            )
            ctx.db.add(m)
            maps[rc.external_id] = m
        m.external_name, m.last_seen_at = rc.name, stamp
    ctx.db.flush()
    return list(maps.values())


def _hash(data: dict) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _match(ctx: Ctx, org_id: int, ra: RemoteAsset, integration_id: int) -> Asset | None:
    """Find the asset this vendor record describes: normalized serial first, then (only when a
    serial is missing on either side) the hostname within the same client."""
    serial = asvc.normalize_serial(ra.serial)
    candidates = list(ctx.db.scalars(select(Asset).where(Asset.organization_id == org_id)))
    if serial:
        hits = [a for a in candidates if a.serial_norm == serial]
        if hits:
            return hits[0]
    name = ra.name.strip().lower()
    for a in candidates:
        if a.name.strip().lower() != name:
            continue
        if serial and a.serial_norm:
            continue  # both have serials and they differ: different devices
        if any(s.integration_id == integration_id for s in a.sources):
            continue  # that vendor already reports a different record under this name
        return a
    return None


def _apply_client(
    ctx: Ctx,
    integration: Integration,
    org_id: int,
    assets: list[RemoteAsset],
    kinds: dict[int, str],
) -> tuple[int, int]:
    added = changed = 0
    stamp = now()
    for ra in assets:
        data = ra.as_data()
        digest = _hash(data)
        source = ctx.db.scalar(
            select(AssetSource).where(
                AssetSource.integration_id == integration.id,
                AssetSource.external_id == ra.external_id,
            )
        )
        if source is not None and source.organization_id != org_id:
            ctx.db.delete(source)  # the vendor client was re-mapped to a different PSA client
            ctx.db.flush()
            source = None
        if source is not None:
            asset = ctx.db.get(Asset, source.asset_id)
            if source.data_hash != digest:
                source.data, source.data_hash = data, digest
                changed += 1
            source.last_seen_at = stamp
        else:
            asset = _match(ctx, org_id, ra, integration.id)
            if asset is None:
                asset = Asset(
                    organization_id=org_id,
                    kind=ra.kind,
                    name=ra.name,
                    first_seen_at=stamp,
                    last_seen_at=stamp,
                )
                ctx.db.add(asset)
                ctx.db.flush()
                added += 1
            else:
                changed += 1
            asset.sources.append(
                AssetSource(
                    organization_id=org_id,
                    integration_id=integration.id,
                    external_id=ra.external_id,
                    data=data,
                    data_hash=digest,
                    first_seen_at=stamp,
                    last_seen_at=stamp,
                )
            )
        asset.retired_at = None
        ctx.db.flush()
        ctx.db.refresh(asset)
        before = (
            asset.name,
            asset.kind,
            asset.manufacturer,
            asset.model,
            asset.serial,
            asset.warranty_start,
            asset.warranty_end,
        )
        asvc.merge(asset, kinds)
        after = (
            asset.name,
            asset.kind,
            asset.manufacturer,
            asset.model,
            asset.serial,
            asset.warranty_start,
            asset.warranty_end,
        )
        if before[-1] != after[-1] and before[-1] is not None:
            audit.record(
                ctx.db,
                None,
                "asset.warranty_changed",
                asset,
                organization_id=org_id,
                before={"warranty_end": before[-1].isoformat()},
                after={
                    "warranty_end": after[-1].isoformat() if after[-1] else None,
                    "source": integration.name,
                },
            )
    return added, changed


def _retire(ctx: Ctx, org_ids: set[int], days: int) -> int:
    if not org_ids:
        return 0
    cutoff = now() - timedelta(days=days)
    n = 0
    for a in ctx.db.scalars(
        select(Asset).where(Asset.organization_id.in_(org_ids), Asset.retired_at.is_(None))
    ):
        if a.sources and max(s.last_seen_at for s in a.sources) < cutoff:
            a.retired_at = now()
            n += 1
    return n


def _kinds(ctx: Ctx) -> dict[int, str]:
    return {i.id: i.kind for i in ctx.db.scalars(select(Integration))}


def sync_integration(ctx: Ctx, integration: Integration, adapter=None) -> SyncRun:
    """Run one sync. Never raises for a vendor problem: the outcome is on the returned run."""
    run = SyncRun(integration_id=integration.id)
    ctx.db.add(run)
    integration.sync_requested_at = None
    ctx.db.flush()
    try:
        adapter = adapter or registry.build_adapter(integration)
        maps = refresh_clients(ctx, integration, adapter)
    except Exception as exc:  # noqa: BLE001 - any adapter/key failure is a failed run, not a crash
        return _finish(ctx, integration, run, "failed", _safe(exc))

    kinds = _kinds(ctx)
    days = int(integration.config.get("retire_after_days", DEFAULT_RETIRE_DAYS))
    synced_orgs: set[int] = set()
    failures: list[str] = []
    for m in maps:
        if m.ignored or m.psa_organization_id is None:
            continue
        try:
            remote = adapter.list_assets(m.external_id)  # fetch fully BEFORE touching any data
        except Exception as exc:  # noqa: BLE001
            run.clients_failed += 1
            failures.append(f"{m.external_name}: {_safe(exc)}")
            continue
        try:
            with ctx.db.begin_nested():
                added, changed = _apply_client(
                    ctx, integration, m.psa_organization_id, remote, kinds
                )
        except Exception as exc:  # noqa: BLE001
            log.exception("applying %s failed", m.external_name)
            run.clients_failed += 1
            failures.append(f"{m.external_name}: could not be saved ({type(exc).__name__})")
            continue
        run.added += added
        run.changed += changed
        run.clients_synced += 1
        synced_orgs.add(m.psa_organization_id)
    run.retired = _retire(ctx, synced_orgs, days)
    if failures:
        status = "failed" if run.clients_synced == 0 else "partial"
        return _finish(ctx, integration, run, status, "; ".join(failures)[:2000])
    return _finish(ctx, integration, run, "ok", None)


def _safe(exc: Exception) -> str:
    """Only vendor errors (already free of secrets) show their message; anything else shows just
    its type, so an unexpected exception can never carry a credential into the UI or audit log."""
    return str(exc) if isinstance(exc, VendorError) else type(exc).__name__


def _finish(
    ctx: Ctx, integration: Integration, run: SyncRun, status: str, error: str | None
) -> SyncRun:
    run.status, run.error, run.finished_at = status, error, now()
    integration.status = "error" if status == "failed" else "ok"
    integration.last_error = error
    if status != "failed":
        integration.last_sync_at = run.finished_at
    if status != "ok":
        audit.record(
            ctx.db,
            None,
            "integration.sync_failed" if status == "failed" else "integration.sync_partial",
            integration,
            detail={"integration": integration.name, "error": error},
        )
    ctx.db.flush()
    return run


def due(ctx: Ctx) -> list[Integration]:
    """Enabled integrations that were asked to sync now or are past their interval."""
    out = []
    t = now()
    for i in ctx.db.scalars(select(Integration).where(Integration.enabled.is_(True))):
        hours = float(i.config.get("sync_hours", 6))
        if (
            i.sync_requested_at
            or i.last_sync_at is None
            or t - i.last_sync_at >= timedelta(hours=hours)
        ):
            # a failing integration backs off to the same interval (last attempt = latest run)
            last = ctx.db.scalar(
                select(SyncRun.started_at)
                .where(SyncRun.integration_id == i.id)
                .order_by(SyncRun.id.desc())
                .limit(1)
            )
            if i.sync_requested_at or last is None or t - last >= timedelta(hours=hours):
                out.append(i)
    return out
