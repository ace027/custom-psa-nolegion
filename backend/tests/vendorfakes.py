"""In-memory stand-ins for vendors. No test touches a real API."""

from collections import defaultdict
from datetime import date

import pytest

from app import db as dbmod
from app.asset_sync import sync_integration
from app.deps import Ctx
from app.integrations import registry
from app.integrations.base import RemoteAsset, RemoteClient, VendorError
from app.models import Integration
from app.scope import Scope


class FakeVendor:
    """Adapter double. `clients` maps external id -> name; `assets` maps client id -> records."""

    def __init__(self):
        self.clients: dict[str, str] = {}
        self.assets: dict[str, list[RemoteAsset]] = {}
        self.fail_clients = False
        self.fail_assets: set[str] = set()
        self.fail_test = False

    def test_connection(self):
        if self.fail_test:
            raise VendorError("NinjaOne sign-in failed (HTTP 401)")

    def list_clients(self):
        if self.fail_clients:
            raise VendorError("vendor is down")
        return [RemoteClient(k, v) for k, v in self.clients.items()]

    def list_assets(self, client_id):
        if client_id in self.fail_assets:
            raise VendorError("vendor timed out")
        return list(self.assets.get(client_id, []))


def dev(ext, name="PC-1", serial="SN-ABCD-1234", kind="computer", end=None, **kw):
    return RemoteAsset(
        external_id=ext,
        name=name,
        kind=kind,
        serial=serial,
        manufacturer=kw.pop("manufacturer", "Dell"),
        model=kw.pop("model", "Latitude"),
        warranty_end=end if end is None or isinstance(end, date) else date.fromisoformat(end),
        **kw,
    )


@pytest.fixture
def vendors(monkeypatch):
    """One FakeVendor per integration id, handed out by build_adapter."""
    fakes: dict[int, FakeVendor] = defaultdict(FakeVendor)

    def build(integration: Integration):
        return fakes[integration.id]

    monkeypatch.setattr(registry, "build_adapter", build)
    return fakes


def run_sync(integration_id: int, adapter=None):
    """Run the worker's sync the way the worker does, in its own transaction."""
    with dbmod.new_session() as db:
        dbmod.set_org_scope(db, "all")
        ctx = Ctx(db=db, user=None, scope=Scope.all())
        run = sync_integration(ctx, db.get(Integration, integration_id), adapter)
        db.commit()
        return {c.key: getattr(run, c.key) for c in type(run).__table__.columns}


NINJA = {
    "kind": "ninjaone",
    "name": "NinjaOne",
    "base_url": "https://app.ninjarmm.com",
    "credentials": {"client_id": "cid-123", "client_secret": "super-secret-value"},
}
HUDU = {
    "kind": "hudu",
    "name": "Hudu",
    "base_url": "https://hudu.example.com",
    "credentials": {"api_key": "hudu-key-abc"},
    "config": {"layouts": {"Switches": "network"}, "warranty_end_field": "Warranty Expiration"},
}
