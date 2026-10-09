"""NinjaOne (read-only). OAuth 2.0 client credentials against the public API.

UNVERIFIED AGAINST A LIVE TENANT: the endpoints and field names below follow NinjaOne's public
API as documented, but the warranty field names could not be confirmed without a real response.
Everything vendor-specific is in `_to_asset`; if the first real sync shows warranty dates
missing, only that function needs adjusting (docs/INTEGRATIONS.md, "First connection").
"""

from datetime import UTC, date, datetime

import httpx

from app.integrations.base import RemoteAsset, RemoteClient, VendorError

PAGE = 200
MAX_PAGES = 500

# nodeClass -> neutral kind
_KINDS = {
    "WINDOWS_WORKSTATION": "computer",
    "MAC": "computer",
    "LINUX_WORKSTATION": "computer",
    "WINDOWS_SERVER": "server",
    "LINUX_SERVER": "server",
    "MAC_SERVER": "server",
    "VMWARE_VM_HOST": "server",
    "HYPERV_VMM_HOST": "server",
    "NMS_SWITCH": "network",
    "NMS_ROUTER": "network",
    "NMS_FIREWALL": "network",
    "NMS_WIRELESS_ACCESS_POINT": "network",
}


def _epoch(value) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(float(value), UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _date(value) -> date | None:
    """NinjaOne gives warranty dates as epoch seconds or ISO strings, depending on the field."""
    if value in (None, "", 0):
        return None
    if isinstance(value, int | float):
        stamp = _epoch(value)
        return stamp.date() if stamp else None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _first(d: dict, *keys):
    for key in keys:
        if d.get(key) not in (None, ""):
            return d[key]
    return None


def _to_asset(d: dict) -> RemoteAsset:
    system = d.get("system") or {}
    warranty = d.get("warranty") or {}
    name = _first(d, "systemName", "dnsName", "displayName") or f"device-{d.get('id')}"
    return RemoteAsset(
        external_id=str(d["id"]),
        name=str(name),
        kind=_KINDS.get(str(d.get("nodeClass", "")).upper(), "other"),
        manufacturer=_first(system, "manufacturer") or _first(d, "manufacturer"),
        model=_first(system, "model") or _first(d, "model"),
        serial=_first(system, "serialNumber", "biosSerialNumber") or _first(d, "serialNumber"),
        warranty_start=_date(_first(warranty, "startDate") or _first(d, "warrantyStartDate")),
        warranty_end=_date(_first(warranty, "endDate") or _first(d, "warrantyEndDate")),
        last_seen=_epoch(d.get("lastContact")),
    )


class NinjaOneClient:
    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base = base_url.rstrip("/")
        self._id = client_id
        self._secret = client_secret
        self._http = httpx.Client(timeout=30, transport=transport)
        self._token: str | None = None

    def _auth(self) -> str:
        if self._token:
            return self._token
        r = self._http.post(
            f"{self.base}/ws/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._id,
                "client_secret": self._secret,
                "scope": "monitoring",
            },
        )
        if r.status_code != 200:
            raise VendorError(f"NinjaOne sign-in failed (HTTP {r.status_code})")
        self._token = r.json().get("access_token")
        if not self._token:
            raise VendorError("NinjaOne sign-in returned no token")
        return self._token

    def _get(self, path: str, params: dict | None = None):
        try:
            r = self._http.get(
                f"{self.base}{path}",
                params=params,
                headers={"Authorization": f"Bearer {self._auth()}"},
            )
        except httpx.HTTPError as exc:
            raise VendorError(f"NinjaOne request failed: {type(exc).__name__}") from exc
        if r.status_code == 401:
            self._token = None
        if r.status_code != 200:
            raise VendorError(f"NinjaOne returned HTTP {r.status_code} for {path}")
        return r.json()

    def test_connection(self) -> None:
        self._get("/v2/organizations", {"pageSize": 1})

    def list_clients(self) -> list[RemoteClient]:
        out: list[RemoteClient] = []
        after = None
        for _ in range(MAX_PAGES):
            params = {"pageSize": PAGE}
            if after is not None:
                params["after"] = after
            page = self._get("/v2/organizations", params)
            out += [RemoteClient(str(o["id"]), str(o.get("name") or o["id"])) for o in page]
            if len(page) < PAGE:
                return out
            after = page[-1]["id"]
        raise VendorError("NinjaOne organization list did not end")

    def list_assets(self, client_external_id: str) -> list[RemoteAsset]:
        out: list[RemoteAsset] = []
        after = None
        for _ in range(MAX_PAGES):
            params = {"df": f"org = {client_external_id}", "pageSize": PAGE}
            if after is not None:
                params["after"] = after
            page = self._get("/v2/devices-detailed", params)
            out += [_to_asset(d) for d in page]
            if len(page) < PAGE:
                return out
            after = page[-1]["id"]
        raise VendorError("NinjaOne device list did not end")
