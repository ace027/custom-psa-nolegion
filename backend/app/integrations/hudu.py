"""Hudu (read-only). API key in the x-api-key header.

Hudu has no built-in warranty field, so the integration config names which asset layouts to
import (and what kind each is) and which field label holds the warranty end date:

  {"layouts": {"Switches": "network", "Firewalls": "network"},
   "warranty_end_field": "Warranty Expiration", "warranty_start_field": null}

Layouts that are not listed are never imported (Hudu also holds documents and applications).
"""

from datetime import date

import httpx

from app.integrations.base import KINDS, RemoteAsset, RemoteClient, VendorError

MAX_PAGES = 1000


def _date(value) -> date | None:
    if not value:
        return None
    text = str(value).strip()[:10]
    for parser in (date.fromisoformat,):
        try:
            return parser(text)
        except ValueError:
            pass
    try:  # MM/DD/YYYY, common in hand-typed Hudu fields
        m, d, y = str(value).strip().split("/")
        return date(int(y), int(m), int(d))
    except ValueError:
        return None


def validate_config(config: dict) -> None:
    layouts = config.get("layouts", {})
    if not isinstance(layouts, dict) or any(k not in KINDS for k in layouts.values()):
        raise ValueError(f"config.layouts must map a layout name to one of {', '.join(KINDS)}")


class HuduClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        config: dict,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base = base_url.rstrip("/")
        self.config = config
        self._http = httpx.Client(timeout=30, transport=transport, headers={"x-api-key": api_key})
        self._layout_kinds: dict[int, str] | None = None

    def _get(self, path: str, params: dict | None = None):
        try:
            r = self._http.get(f"{self.base}/api/v1{path}", params=params)
        except httpx.HTTPError as exc:
            raise VendorError(f"Hudu request failed: {type(exc).__name__}") from exc
        if r.status_code != 200:
            raise VendorError(f"Hudu returned HTTP {r.status_code} for {path}")
        return r.json()

    def _pages(self, path: str, key: str, params: dict | None = None) -> list[dict]:
        """Hudu paginates by page number with no total, so read until an empty page."""
        out: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            body = self._get(path, {**(params or {}), "page": page})
            items = body.get(key, []) if isinstance(body, dict) else body
            if not items:
                return out
            out += items
        raise VendorError("Hudu list did not end")

    def test_connection(self) -> None:
        self._get("/companies", {"page": 1})

    def list_clients(self) -> list[RemoteClient]:
        return [
            RemoteClient(str(c["id"]), str(c.get("name") or c["id"]))
            for c in self._pages("/companies", "companies")
        ]

    def _kinds(self) -> dict[int, str]:
        if self._layout_kinds is None:
            wanted = self.config.get("layouts", {})
            layouts = self._pages("/asset_layouts", "asset_layouts")
            self._layout_kinds = {
                int(lay["id"]): wanted[lay["name"]] for lay in layouts if lay.get("name") in wanted
            }
        return self._layout_kinds

    def list_assets(self, client_external_id: str) -> list[RemoteAsset]:
        kinds = self._kinds()
        end_label = self.config.get("warranty_end_field")
        start_label = self.config.get("warranty_start_field")
        out: list[RemoteAsset] = []
        for a in self._pages("/assets", "assets", {"company_id": client_external_id}):
            kind = kinds.get(int(a.get("asset_layout_id") or 0))
            if kind is None or a.get("archived"):
                continue
            fields = {
                str(f.get("label", "")).strip().lower(): f.get("value") for f in a.get("fields", [])
            }
            out.append(
                RemoteAsset(
                    external_id=str(a["id"]),
                    name=str(a.get("name") or a["id"]),
                    kind=kind,
                    manufacturer=a.get("primary_manufacturer") or None,
                    model=a.get("primary_model") or None,
                    serial=a.get("primary_serial") or None,
                    warranty_end=_date(fields.get(end_label.strip().lower()))
                    if end_label
                    else None,
                    warranty_start=(
                        _date(fields.get(start_label.strip().lower())) if start_label else None
                    ),
                )
            )
        return out
