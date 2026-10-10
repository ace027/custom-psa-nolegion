"""The neutral shape every vendor adapter returns. Adapters only READ from vendors."""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

KINDS = ("computer", "server", "network", "other")


class VendorError(Exception):
    """A vendor call failed. The message must never contain credentials."""


@dataclass
class RemoteClient:
    external_id: str
    name: str


@dataclass
class RemoteAsset:
    external_id: str
    name: str
    kind: str = "other"
    manufacturer: str | None = None
    model: str | None = None
    serial: str | None = None
    warranty_start: date | None = None
    warranty_end: date | None = None
    last_seen: datetime | None = None
    extra: dict = field(default_factory=dict)

    def as_data(self) -> dict:
        """JSON stored on asset_sources (exactly what this vendor reported)."""
        return {
            "name": self.name,
            "kind": self.kind,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "serial": self.serial,
            "warranty_start": self.warranty_start.isoformat() if self.warranty_start else None,
            "warranty_end": self.warranty_end.isoformat() if self.warranty_end else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }


class Adapter(Protocol):
    def test_connection(self) -> None: ...
    def list_clients(self) -> list[RemoteClient]: ...
    def list_assets(self, client_external_id: str) -> list[RemoteAsset]: ...
