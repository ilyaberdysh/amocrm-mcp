"""
AmoCRM API client for MCP server.
Identical to backend version + on_token_refresh callback for auto-saving tokens.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable


def exchange_auth_code(
    subdomain: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    auth_code: str,
) -> dict:
    """Exchange authorization_code for access+refresh tokens."""
    url = f"https://{subdomain}.amocrm.ru/oauth2/access_token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": redirect_uri,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise ValueError(f"AmoCRM auth error {e.code}: {body[:400]}") from e


def refresh_tokens(
    subdomain: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    refresh_token: str,
) -> dict | None:
    """Refresh expired access_token using refresh_token."""
    url = f"https://{subdomain}.amocrm.ru/oauth2/access_token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "redirect_uri": redirect_uri,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError:
        return None


class AmoCRMClient:
    """
    AmoCRM API client.
    on_token_refresh: optional callback(access_token, refresh_token) — called after auto-refresh.
    """

    def __init__(
        self,
        subdomain: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        access_token: str,
        refresh_token: str,
        on_token_refresh: Callable[[str, str], None] | None = None,
    ) -> None:
        self.subdomain = subdomain
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.access_token = access_token
        self.refresh_token = refresh_token
        self._on_token_refresh = on_token_refresh

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get(self, path: str) -> dict | None:
        result = self._raw_get(path, self.access_token)
        if result is None:
            new_tokens = refresh_tokens(
                self.subdomain, self.client_id, self.client_secret,
                self.redirect_uri, self.refresh_token,
            )
            if new_tokens:
                self.access_token = new_tokens["access_token"]
                self.refresh_token = new_tokens.get("refresh_token", self.refresh_token)
                if self._on_token_refresh:
                    self._on_token_refresh(self.access_token, self.refresh_token)
                result = self._raw_get(path, self.access_token)
        return result

    def _raw_get(self, path: str, token: str) -> dict | None:
        url = f"https://{self.subdomain}.amocrm.ru{path}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        delays = [2, 5, 10]
        for attempt in range(len(delays) + 1):
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    body = resp.read().decode()
                    if not body:
                        return None
                    return json.loads(body)
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    return None
                if e.code == 429 and attempt < len(delays):
                    time.sleep(delays[attempt])
                    continue
                body = e.read().decode() if e.fp else ""
                raise RuntimeError(f"AmoCRM API error {e.code} on {path}: {body[:300]}") from e
        return None

    def _paginate(self, path: str, entity_key: str, limit: int = 200) -> list[dict]:
        results: list[dict] = []
        page_size = min(limit, 250)
        page = 1
        while len(results) < limit:
            sep = "&" if "?" in path else "?"
            data = self._get(f"{path}{sep}limit={page_size}&page={page}")
            if not data or "_embedded" not in data:
                break
            items: list[dict] = data["_embedded"].get(entity_key, [])
            results.extend(items)
            if len(items) < page_size:
                break
            page += 1
        return results[:limit]

    # ── Public API ────────────────────────────────────────────────────────────

    def get_account(self) -> dict | None:
        return self._get("/api/v4/account")

    def get_pipelines(self) -> list[dict]:
        data = self._get("/api/v4/leads/pipelines?with=statuses")
        if not data or "_embedded" not in data:
            return []
        return data["_embedded"].get("pipelines", [])

    def get_leads(
        self,
        pipeline_id: int | None = None,
        status_ids: list[int] | None = None,
        responsible_user_ids: list[int] | None = None,
        created_by: list[int] | None = None,
        date_from: int | None = None,
        date_to: int | None = None,
        updated_at_from: int | None = None,
        updated_at_to: int | None = None,
        closed_at_from: int | None = None,
        closed_at_to: int | None = None,
        price_from: int | None = None,
        price_to: int | None = None,
        query: str | None = None,
        order_by: str | None = None,
        order_dir: str = "desc",
        with_contacts: bool = False,
        with_companies: bool = False,
        with_loss_reason: bool = False,
        with_tasks: bool = False,
        with_catalog_elements: bool = False,
        limit: int = 200,
    ) -> list[dict]:
        params: list[str] = []
        if pipeline_id:
            params.append(f"filter[pipeline_id]={pipeline_id}")
        if status_ids:
            for sid in status_ids:
                params.append(f"filter[status_id][]={sid}")
        if responsible_user_ids:
            for uid in responsible_user_ids:
                params.append(f"filter[responsible_user_id][]={uid}")
        if created_by:
            for uid in created_by:
                params.append(f"filter[created_by][]={uid}")
        if date_from:
            params.append(f"filter[created_at][from]={date_from}")
        if date_to:
            params.append(f"filter[created_at][to]={date_to}")
        if updated_at_from:
            params.append(f"filter[updated_at][from]={updated_at_from}")
        if updated_at_to:
            params.append(f"filter[updated_at][to]={updated_at_to}")
        if closed_at_from:
            params.append(f"filter[closed_at][from]={closed_at_from}")
        if closed_at_to:
            params.append(f"filter[closed_at][to]={closed_at_to}")
        if price_from is not None:
            params.append(f"filter[price][from]={price_from}")
        if price_to is not None:
            params.append(f"filter[price][to]={price_to}")
        if query:
            params.append(f"query={urllib.parse.quote(query)}")
        if order_by:
            params.append(f"order[{order_by}]={order_dir}")
        with_parts: list[str] = []
        if with_contacts:
            with_parts.append("contacts")
        if with_companies:
            with_parts.append("companies")
        if with_loss_reason:
            with_parts.append("loss_reason")
        if with_tasks:
            with_parts.append("tasks")
        if with_catalog_elements:
            with_parts.append("catalog_elements")
        if with_parts:
            params.append("with=" + ",".join(with_parts))
        base = "/api/v4/leads?" + "&".join(params) if params else "/api/v4/leads"
        return self._paginate(base, "leads", limit=min(limit, 200))

    def count_and_sum_leads(
        self,
        pipeline_id: int | None = None,
        status_ids: list[int] | None = None,
        responsible_user_ids: list[int] | None = None,
        created_by: list[int] | None = None,
        date_from: int | None = None,
        date_to: int | None = None,
        updated_at_from: int | None = None,
        updated_at_to: int | None = None,
        closed_at_from: int | None = None,
        closed_at_to: int | None = None,
        price_from: int | None = None,
        price_to: int | None = None,
        query: str | None = None,
        exclude_closed: bool = False,
    ) -> dict:
        """Fetch ALL leads matching filters, return only counts and sums."""
        params: list[str] = []
        if pipeline_id:
            params.append(f"filter[pipeline_id]={pipeline_id}")
        if status_ids:
            for sid in status_ids:
                params.append(f"filter[status_id][]={sid}")
        if responsible_user_ids:
            for uid in responsible_user_ids:
                params.append(f"filter[responsible_user_id][]={uid}")
        if created_by:
            for uid in created_by:
                params.append(f"filter[created_by][]={uid}")
        if date_from:
            params.append(f"filter[created_at][from]={date_from}")
        if date_to:
            params.append(f"filter[created_at][to]={date_to}")
        if updated_at_from:
            params.append(f"filter[updated_at][from]={updated_at_from}")
        if updated_at_to:
            params.append(f"filter[updated_at][to]={updated_at_to}")
        if closed_at_from:
            params.append(f"filter[closed_at][from]={closed_at_from}")
        if closed_at_to:
            params.append(f"filter[closed_at][to]={closed_at_to}")
        if price_from is not None:
            params.append(f"filter[price][from]={price_from}")
        if price_to is not None:
            params.append(f"filter[price][to]={price_to}")
        if query:
            params.append(f"query={urllib.parse.quote(query)}")

        base = "/api/v4/leads?" + "&".join(params) if params else "/api/v4/leads"
        leads = self._paginate(base, "leads", limit=10000)

        if exclude_closed:
            leads = [l for l in leads if l.get("status_id") not in (142, 143)]

        by_pipeline: dict[int, dict] = {}
        total_price = 0
        for lead in leads:
            price = lead.get("price", 0) or 0
            total_price += price
            pid = lead.get("pipeline_id", 0)
            if pid not in by_pipeline:
                by_pipeline[pid] = {"pipeline_id": pid, "count": 0, "total_price": 0}
            by_pipeline[pid]["count"] += 1
            by_pipeline[pid]["total_price"] += price

        return {
            "count": len(leads),
            "total_price": total_price,
            "by_pipeline": list(by_pipeline.values()),
        }

    def get_leads_grouped_by_company(
        self,
        pipeline_id: int | None = None,
        status_ids: list[int] | None = None,
        responsible_user_ids: list[int] | None = None,
        exclude_closed: bool = False,
        closed_at_from: int | None = None,
        closed_at_to: int | None = None,
        date_from: int | None = None,
        date_to: int | None = None,
        top: int = 50,
    ) -> list[dict]:
        """Fetch ALL leads, group by company, return top-N by total_price."""
        params: list[str] = []
        if pipeline_id:
            params.append(f"filter[pipeline_id]={pipeline_id}")
        if status_ids:
            for sid in status_ids:
                params.append(f"filter[status_id][]={sid}")
        if responsible_user_ids:
            for uid in responsible_user_ids:
                params.append(f"filter[responsible_user_id][]={uid}")
        if date_from:
            params.append(f"filter[created_at][from]={date_from}")
        if date_to:
            params.append(f"filter[created_at][to]={date_to}")
        if closed_at_from:
            params.append(f"filter[closed_at][from]={closed_at_from}")
        if closed_at_to:
            params.append(f"filter[closed_at][to]={closed_at_to}")
        params.append("with=companies,contacts")

        base = "/api/v4/leads?" + "&".join(params) if params else "/api/v4/leads?with=companies,contacts"
        leads = self._paginate(base, "leads", limit=10000)

        if exclude_closed:
            leads = [l for l in leads if l.get("status_id") not in (142, 143)]

        groups: dict[int, dict] = {}
        for lead in leads:
            embedded = lead.get("_embedded") or {}
            companies = embedded.get("companies") or []
            cid = companies[0]["id"] if companies else 0
            price = lead.get("price", 0) or 0
            rid = lead.get("responsible_user_id", 0)
            contacts = embedded.get("contacts") or []
            contact_id = contacts[0]["id"] if contacts else 0

            if cid not in groups:
                groups[cid] = {
                    "company_id": cid,
                    "total_price": 0,
                    "deals_count": 0,
                    "manager_ids": set(),
                    "main_contact_id": contact_id,
                }
            g = groups[cid]
            g["total_price"] += price
            g["deals_count"] += 1
            if rid:
                g["manager_ids"].add(rid)
            if not g["main_contact_id"] and contact_id:
                g["main_contact_id"] = contact_id

        # Sort by total_price DESC, take top-N
        sorted_groups = sorted(groups.values(), key=lambda x: x["total_price"], reverse=True)[:top]

        # Fetch company names for top-N
        for g in sorted_groups:
            cid = g["company_id"]
            if cid == 0:
                g["company_name"] = "Без компании"
            else:
                data = self._get(f"/api/v4/companies/{cid}")
                g["company_name"] = (data or {}).get("name", f"ID {cid}")
            g["avg_price"] = g["total_price"] // g["deals_count"] if g["deals_count"] else 0
            g["manager_ids"] = list(g["manager_ids"])

        return sorted_groups

    def get_contacts(
        self,
        query: str = "",
        responsible_user_ids: list[int] | None = None,
        created_at_from: int | None = None,
        created_at_to: int | None = None,
        updated_at_from: int | None = None,
        updated_at_to: int | None = None,
        with_leads: bool = False,
        with_customers: bool = False,
        limit: int = 200,
    ) -> list[dict]:
        params: list[str] = []
        if query:
            params.append(f"query={urllib.parse.quote(query)}")
        if responsible_user_ids:
            for uid in responsible_user_ids:
                params.append(f"filter[responsible_user_id][]={uid}")
        if created_at_from:
            params.append(f"filter[created_at][from]={created_at_from}")
        if created_at_to:
            params.append(f"filter[created_at][to]={created_at_to}")
        if updated_at_from:
            params.append(f"filter[updated_at][from]={updated_at_from}")
        if updated_at_to:
            params.append(f"filter[updated_at][to]={updated_at_to}")
        with_parts: list[str] = []
        if with_leads:
            with_parts.append("leads")
        if with_customers:
            with_parts.append("customers")
        if with_parts:
            params.append("with=" + ",".join(with_parts))
        base = "/api/v4/contacts?" + "&".join(params) if params else "/api/v4/contacts"
        return self._paginate(base, "contacts", limit=min(limit, 200))

    def get_companies(
        self,
        query: str = "",
        responsible_user_ids: list[int] | None = None,
        created_at_from: int | None = None,
        created_at_to: int | None = None,
        updated_at_from: int | None = None,
        updated_at_to: int | None = None,
        with_leads: bool = False,
        with_contacts: bool = False,
        limit: int = 200,
    ) -> list[dict]:
        params: list[str] = []
        if query:
            params.append(f"query={urllib.parse.quote(query)}")
        if responsible_user_ids:
            for uid in responsible_user_ids:
                params.append(f"filter[responsible_user_id][]={uid}")
        if created_at_from:
            params.append(f"filter[created_at][from]={created_at_from}")
        if created_at_to:
            params.append(f"filter[created_at][to]={created_at_to}")
        if updated_at_from:
            params.append(f"filter[updated_at][from]={updated_at_from}")
        if updated_at_to:
            params.append(f"filter[updated_at][to]={updated_at_to}")
        with_parts: list[str] = []
        if with_leads:
            with_parts.append("leads")
        if with_contacts:
            with_parts.append("contacts")
        if with_parts:
            params.append("with=" + ",".join(with_parts))
        base = "/api/v4/companies?" + "&".join(params) if params else "/api/v4/companies"
        return self._paginate(base, "companies", limit=min(limit, 200))

    def get_notes(
        self,
        entity_type: str = "leads",
        entity_ids: list[int] | None = None,
        note_types: list[str] | None = None,
        created_at_from: int | None = None,
        created_at_to: int | None = None,
        updated_at_from: int | None = None,
        updated_at_to: int | None = None,
        limit: int = 200,
    ) -> list[dict]:
        params: list[str] = []
        if entity_ids:
            for eid in entity_ids:
                params.append(f"filter[entity_id][]={eid}")
        if note_types:
            for t in note_types:
                params.append(f"filter[note_type][]={t}")
        if created_at_from:
            params.append(f"filter[created_at][from]={created_at_from}")
        if created_at_to:
            params.append(f"filter[created_at][to]={created_at_to}")
        if updated_at_from:
            params.append(f"filter[updated_at][from]={updated_at_from}")
        if updated_at_to:
            params.append(f"filter[updated_at][to]={updated_at_to}")
        base = f"/api/v4/{entity_type}/notes?" + "&".join(params) if params else f"/api/v4/{entity_type}/notes"
        return self._paginate(base, "notes", limit=min(limit, 200))

    def get_customers(
        self,
        responsible_user_ids: list[int] | None = None,
        created_at_from: int | None = None,
        created_at_to: int | None = None,
        updated_at_from: int | None = None,
        updated_at_to: int | None = None,
        with_contacts: bool = False,
        with_companies: bool = False,
        limit: int = 200,
    ) -> list[dict]:
        params: list[str] = []
        if responsible_user_ids:
            for uid in responsible_user_ids:
                params.append(f"filter[responsible_user_id][]={uid}")
        if created_at_from:
            params.append(f"filter[created_at][from]={created_at_from}")
        if created_at_to:
            params.append(f"filter[created_at][to]={created_at_to}")
        if updated_at_from:
            params.append(f"filter[updated_at][from]={updated_at_from}")
        if updated_at_to:
            params.append(f"filter[updated_at][to]={updated_at_to}")
        with_parts: list[str] = []
        if with_contacts:
            with_parts.append("contacts")
        if with_companies:
            with_parts.append("companies")
        if with_parts:
            params.append("with=" + ",".join(with_parts))
        base = "/api/v4/customers?" + "&".join(params) if params else "/api/v4/customers"
        return self._paginate(base, "customers", limit=min(limit, 200))

    def get_unsorted(
        self,
        pipeline_id: int | None = None,
        category: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        params: list[str] = []
        if pipeline_id:
            params.append(f"filter[pipeline_id][]={pipeline_id}")
        if category:
            params.append(f"filter[category][]={category}")
        base = "/api/v4/leads/unsorted?" + "&".join(params) if params else "/api/v4/leads/unsorted"
        return self._paginate(base, "unsorted", limit=min(limit, 200))

    def get_catalogs(self) -> list[dict]:
        data = self._get("/api/v4/catalogs")
        if not data or "_embedded" not in data:
            return []
        return data["_embedded"].get("catalogs", [])

    def get_catalog_elements(self, catalog_id: int, query: str = "", limit: int = 200) -> list[dict]:
        path = f"/api/v4/catalogs/{catalog_id}/elements"
        if query:
            path += f"?query={urllib.parse.quote(query)}"
        return self._paginate(path, "elements", limit=min(limit, 200))

    def get_events(
        self,
        entity_type: str | None = None,
        event_types: list[str] | None = None,
        date_from: int | None = None,
        date_to: int | None = None,
        limit: int = 200,
    ) -> list[dict]:
        # AmoCRM Events API uses singular entity names
        _entity_map = {"leads": "lead", "contacts": "contact", "companies": "company"}
        params: list[str] = []
        if entity_type:
            mapped = _entity_map.get(entity_type, entity_type)
            params.append(f"filter[entity][]={mapped}")
        if event_types:
            for t in event_types:
                params.append(f"filter[type][]={t}")
        if date_from:
            params.append(f"filter[created_at][from]={date_from}")
        if date_to:
            params.append(f"filter[created_at][to]={date_to}")
        base = "/api/v4/events?" + "&".join(params) if params else "/api/v4/events"
        return self._paginate(base, "events", limit=min(limit, 100))

    def get_tasks(
        self,
        responsible_user_ids: list[int] | None = None,
        is_completed: bool | None = None,
        date_from: int | None = None,
        date_to: int | None = None,
        complete_till_from: int | None = None,
        complete_till_to: int | None = None,
        order_by: str | None = "complete_till",
        order_dir: str | None = "asc",
        limit: int = 200,
    ) -> list[dict]:
        params: list[str] = []
        if responsible_user_ids:
            for uid in responsible_user_ids:
                params.append(f"filter[responsible_user_id][]={uid}")
        if is_completed is not None:
            params.append(f"filter[is_completed]={1 if is_completed else 0}")
        if date_from:
            params.append(f"filter[created_at][from]={date_from}")
        if date_to:
            params.append(f"filter[created_at][to]={date_to}")
        if complete_till_from:
            params.append(f"filter[complete_till][from]={complete_till_from}")
        if complete_till_to:
            params.append(f"filter[complete_till][to]={complete_till_to}")
        if order_by:
            params.append(f"order[{order_by}]={order_dir or 'asc'}")
        base = "/api/v4/tasks?" + "&".join(params) if params else "/api/v4/tasks"
        return self._paginate(base, "tasks", limit=min(limit, 200))

    def get_users(self) -> list[dict]:
        data = self._get("/api/v4/users?with=group&limit=250")
        if not data or "_embedded" not in data:
            return []
        return data["_embedded"].get("users", [])

    def get_custom_fields(self, entity: str = "leads") -> list[dict]:
        data = self._get(f"/api/v4/{entity}/custom_fields?limit=250")
        if not data or "_embedded" not in data:
            return []
        return data["_embedded"].get("custom_fields", [])

    def get_loss_reasons(self) -> list[dict]:
        data = self._get("/api/v4/leads/loss_reasons")
        if not data or "_embedded" not in data:
            return []
        return [{"id": r["id"], "name": r.get("name", "")} for r in data["_embedded"].get("loss_reasons", [])]

    def get_tags(self, entity: str = "leads") -> list[dict]:
        data = self._get(f"/api/v4/{entity}/tags?limit=250")
        if not data or "_embedded" not in data:
            return []
        return data["_embedded"].get("tags", [])

    def get_sources(self) -> list[dict]:
        data = self._get("/api/v4/sources")
        if not data or "_embedded" not in data:
            return []
        return data["_embedded"].get("sources", [])
