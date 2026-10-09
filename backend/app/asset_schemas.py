"""API shapes for vendor integrations, assets and the warranty report."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

IntegrationKind = Literal["ninjaone", "hudu"]
AssetKind = Literal["computer", "server", "network", "other"]
WarrantyState = Literal[
    "expired", "expiring_30", "expiring_60", "expiring_90", "in_warranty", "unknown"
]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class IntegrationIn(BaseModel):
    kind: IntegrationKind
    name: str = Field(min_length=1, max_length=100)
    base_url: str = Field(min_length=8, max_length=300, pattern=r"^https://")
    # ninjaone: {client_id, client_secret}; hudu: {api_key}. Write-only: never returned.
    credentials: dict[str, str]
    config: dict = Field(default_factory=dict)


class IntegrationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    base_url: str | None = Field(default=None, min_length=8, max_length=300, pattern=r"^https://")
    credentials: dict[str, str] | None = None
    config: dict | None = None
    enabled: bool | None = None


class IntegrationOut(BaseModel):
    id: int
    kind: str
    name: str
    base_url: str
    config: dict
    credentials_set: bool
    credentials_set_at: datetime | None
    enabled: bool
    status: str
    last_error: str | None
    last_sync_at: datetime | None
    sync_requested: bool


class TestOut(BaseModel):
    ok: bool
    error: str | None


class SyncRunOut(ORM):
    id: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    added: int
    changed: int
    retired: int
    clients_synced: int
    clients_failed: int
    error: str | None


class ClientMapOut(BaseModel):
    id: int
    external_id: str
    external_name: str
    organization_id: int | None
    ignored: bool
    needs_mapping: bool
    suggested_organization_id: int | None
    first_seen_at: datetime


class ClientMapIn(BaseModel):
    organization_id: int | None = None
    ignored: bool = False


class AssetOut(BaseModel):
    id: int
    organization_id: int
    organization_name: str
    kind: str
    name: str
    manufacturer: str | None
    model: str | None
    serial: str | None
    warranty_start: date | None
    warranty_end: date | None
    warranty_status: WarrantyState
    warranty_overridden: bool
    conflict: bool
    first_seen_at: datetime
    last_seen_at: datetime
    retired_at: datetime | None


class SourceOut(BaseModel):
    integration: str
    external_id: str
    data: dict
    last_seen_at: datetime


class OverrideOut(BaseModel):
    field: str
    value: date
    reason: str
    created_by: int | None
    updated_at: datetime


class AssetDetailOut(AssetOut):
    sources: list[SourceOut]
    overrides: list[OverrideOut]


class OverrideIn(BaseModel):
    value: date
    reason: str = Field(min_length=1, max_length=1000)


class WarrantyReportOut(BaseModel):
    as_of: date
    total: int
    counts: dict[str, int]
    rows: list[AssetOut]


class SharingIn(BaseModel):
    published: bool


class SharingOut(BaseModel):
    organization_id: int
    published: bool


# ---- portal ----
class PortalAssetOut(BaseModel):
    name: str
    kind: str
    manufacturer: str | None
    model: str | None
    warranty_end: date | None
    warranty_status: WarrantyState


class PortalAssetsOut(BaseModel):
    as_of: date
    total: int
    counts: dict[str, int]
    devices: list[PortalAssetOut]
