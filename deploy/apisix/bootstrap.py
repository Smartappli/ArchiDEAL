"""Install the idempotent ArchiDEAL routes through the APISIX Admin API."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ADMIN_URL = os.environ.get("APISIX_ADMIN_URL", "http://apisix:9180").rstrip("/")
ADMIN_KEY = os.environ["APISIX_ADMIN_KEY"]
ROUTES_FILE = Path(os.environ.get("APISIX_ROUTES_FILE", "/bootstrap/routes.json"))
PLUGIN_METADATA_FILE = os.environ.get("APISIX_PLUGIN_METADATA_FILE", "").strip()
MANAGED_ROUTE_PREFIX = "archideal-"


def request(path: str, *, method: str = "GET", payload: dict | None = None) -> int:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"X-API-KEY": ADMIN_KEY, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(f"{ADMIN_URL}{path}", data=body, headers=headers, method=method)
    with urlopen(req, timeout=5) as response:
        response.read()
        return response.status


def request_json(path: str) -> tuple[int, dict]:
    """Return one authenticated APISIX Admin API JSON response."""
    req = Request(
        f"{ADMIN_URL}{path}",
        headers={"X-API-KEY": ADMIN_KEY, "Accept": "application/json"},
        method="GET",
    )
    with urlopen(req, timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("APISIX Admin API returned a non-object response")
        return response.status, payload


def wait_for_admin_api() -> None:
    for attempt in range(60):
        try:
            request("/apisix/admin/routes?page=1&page_size=10")
            return
        except (HTTPError, URLError, TimeoutError, ConnectionError):
            if attempt == 59:
                raise RuntimeError("APISIX Admin API did not become ready")
            time.sleep(2)


def install_plugin_metadata() -> None:
    """Install optional production observability metadata before routes."""
    if not PLUGIN_METADATA_FILE:
        return
    metadata = json.loads(Path(PLUGIN_METADATA_FILE).read_text(encoding="utf-8"))
    for plugin_name, payload in metadata.get("plugin_metadata", {}).items():
        status = request(
            f"/apisix/admin/plugin_metadata/{quote(plugin_name, safe='')}",
            method="PUT",
            payload=payload,
        )
        if status not in {200, 201}:
            raise RuntimeError(
                f"Unexpected APISIX status {status} for plugin {plugin_name}"
            )


def installed_managed_route_ids() -> set[str]:
    """List route IDs reserved for this bootstrap, following Admin API pagination."""
    page = 1
    page_size = 100
    route_ids: set[str] = set()
    while True:
        status, payload = request_json(
            f"/apisix/admin/routes?page={page}&page_size={page_size}",
        )
        if status != 200:
            raise RuntimeError(f"Unexpected APISIX route-list status {status}")
        items = payload.get("list")
        if not isinstance(items, list):
            raise RuntimeError("APISIX route-list response has no list")
        for item in items:
            if not isinstance(item, dict):
                continue
            value = item.get("value")
            route_id = value.get("id") if isinstance(value, dict) else None
            if not route_id:
                key = str(item.get("key", ""))
                route_id = key.rsplit("/", 1)[-1]
            route_id = str(route_id)
            if route_id.startswith(MANAGED_ROUTE_PREFIX):
                route_ids.add(route_id)

        total = payload.get("total", len(items))
        if not isinstance(total, int) or total < 0:
            raise RuntimeError("APISIX route-list response has an invalid total")
        if page * page_size >= total or not items:
            return route_ids
        page += 1


def remove_stale_managed_routes(desired_route_ids: set[str]) -> None:
    """Delete obsolete routes in the reserved ArchiDEAL bootstrap namespace."""
    for route_id in sorted(installed_managed_route_ids() - desired_route_ids):
        route_ref = quote(route_id, safe="")
        status = request(f"/apisix/admin/routes/{route_ref}", method="DELETE")
        if status not in {200, 204}:
            raise RuntimeError(
                f"Unexpected APISIX status {status} deleting route {route_ref}",
            )
        print(f"removed stale route {route_ref}")


def main() -> None:
    routes = json.loads(ROUTES_FILE.read_text(encoding="utf-8"))["routes"]
    desired_route_ids = {str(route["id"]) for route in routes}
    if len(desired_route_ids) != len(routes):
        raise RuntimeError("Bootstrap route IDs must be unique")
    if not desired_route_ids or not all(
        route_id.startswith(MANAGED_ROUTE_PREFIX) for route_id in desired_route_ids
    ):
        raise RuntimeError(
            f"Bootstrap route IDs must use the reserved {MANAGED_ROUTE_PREFIX!r} prefix",
        )
    wait_for_admin_api()
    install_plugin_metadata()
    for route in routes:
        route_id = quote(str(route["id"]), safe="")
        status = request(
            f"/apisix/admin/routes/{route_id}",
            method="PUT",
            payload={key: value for key, value in route.items() if key != "id"},
        )
        if status not in {200, 201}:
            raise RuntimeError(f"Unexpected APISIX status {status} for route {route_id}")
        print(f"installed route {route_id}")
    remove_stale_managed_routes(desired_route_ids)


if __name__ == "__main__":
    main()
