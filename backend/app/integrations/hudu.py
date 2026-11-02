"""Hudu (read-only). API key in the x-api-key header.

Hudu has no built-in warranty field, so the integration config names which asset layouts to
import (and what kind each is) and which field label holds the warranty end date:

  {"layouts": {"Switches": "network", "Firewalls": "network"},
   "warranty_end_field": "Warranty Expiration", "warranty_start_field": null}

Layouts that are not listed are never imported (Hudu also holds documents and applications).
Ticket pages also search Hudu articles (`search_articles`), returning references only.
"""

from datetime import UTC, date, datetime
from urllib.parse import urljoin, urlsplit

import httpx

from app.integrations.base import KINDS, RemoteArticle, RemoteAsset, RemoteClient, VendorError

MAX_PAGES = 1000
SEARCH_TIMEOUT = 5  # seconds per article request: a ticket page is waiting on it
SEARCH_PAGE_SIZE = 25
OLDEST = datetime.min.replace(tzinfo=UTC)


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

    def _get(self, path: str, params: dict | None = None, timeout=httpx.USE_CLIENT_DEFAULT):
        try:
            r = self._http.get(f"{self.base}/api/v1{path}", params=params, timeout=timeout)
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

    def _article(self, a: dict, scope: str) -> RemoteArticle | None:
        if not a.get("id") or not a.get("url"):
            return None
        url = str(a["url"])
        if not urlsplit(url).scheme:  # relative: under the configured Hudu base URL
            url = urljoin(self.base + "/", url.lstrip("/"))
        if urlsplit(url).scheme not in ("http", "https"):  # never hand the browser javascript: etc.
            return None
        try:
            updated = datetime.fromisoformat(str(a.get("updated_at") or ""))
            updated = updated if updated.tzinfo else updated.replace(tzinfo=UTC)
        except ValueError:
            updated = None
        return RemoteArticle(str(a["id"]), str(a.get("name") or "Untitled"), url, updated, scope)

    def search_articles(
        self, query: str, company_external_id: str | None, limit: int = 5
    ) -> list[RemoteArticle]:
        """Articles matching `query` in the company plus global ones (no company), newest first.

        UNVERIFIED AGAINST A LIVE TENANT: GET /api/v1/articles with search, company_id, page and
        page_size, and the article fields id, name, url, company_id, updated_at, follow Hudu's
        public API docs. Hudu cannot filter on "no company", so global articles come from an
        unfiltered search keeping company_id null; company results are re-checked by company_id.
        shortcut: only the first page of each search is read; page further if matches get missed.
        """
        searches = [("global", None)]
        if company_external_id:
            searches.insert(0, ("client", str(company_external_id)))
        found: dict[str, RemoteArticle] = {}
        for scope, company in searches:
            params = {"search": query, "page": 1, "page_size": SEARCH_PAGE_SIZE}
            if company:
                params["company_id"] = company
            body = self._get("/articles", params, timeout=SEARCH_TIMEOUT)
            for a in body.get("articles", []) if isinstance(body, dict) else body:
                owner = a.get("company_id")
                if (str(owner) if owner is not None else None) != company:
                    continue
                article = self._article(a, scope)
                if article and article.id not in found:
                    found[article.id] = article
        newest = sorted(found.values(), key=lambda x: x.updated_at or OLDEST, reverse=True)
        return newest[:limit]
