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


def request(path: str, *, method: str = "GET", payload: dict | None = None) -> int:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"X-API-KEY": ADMIN_KEY, "Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(f"{ADMIN_URL}{path}", data=body, headers=headers, method=method)
    with urlopen(req, timeout=5) as response:
        response.read()
        return response.status


def wait_for_admin_api() -> None:
    for attempt in range(60):
        try:
            request("/apisix/admin/routes?page=1&page_size=10")
            return
        except (HTTPError, URLError, TimeoutError, ConnectionError):
            if attempt == 59:
                raise RuntimeError("APISIX Admin API did not become ready")
            time.sleep(2)


def main() -> None:
    routes = json.loads(ROUTES_FILE.read_text(encoding="utf-8"))["routes"]
    wait_for_admin_api()
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


if __name__ == "__main__":
    main()
