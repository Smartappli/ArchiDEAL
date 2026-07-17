from __future__ import annotations

from typing import Any

import httpx


class DealHostClient:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        with httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=headers,
        ) as client:
            response = client.request(method=method, url=path, json=json, params=params)
            response.raise_for_status()
            return response.json()

    def create_tool(
        self,
        *,
        name: str,
        slug: str,
        description: str = "",
        module_ids: list[int] | None = None,
        enabled: bool = True,
    ) -> Any:
        return self._request(
            "POST",
            "/api/hosting/tools/",
            json={
                "name": name,
                "slug": slug,
                "description": description,
                "module_ids": module_ids or [],
                "enabled": enabled,
            },
        )

    def create_application(
        self,
        *,
        name: str,
        slug: str,
        description: str = "",
        module_ids: list[int] | None = None,
        enabled: bool = True,
    ) -> Any:
        return self._request(
            "POST",
            "/api/hosting/applications/",
            json={
                "name": name,
                "slug": slug,
                "description": description,
                "module_ids": module_ids or [],
                "enabled": enabled,
            },
        )

    def list_tools(
        self,
        *,
        enabled: bool | None = None,
        module_slug: str | None = None,
    ) -> Any:
        params: dict[str, Any] = {}
        if enabled is not None:
            params["enabled"] = str(enabled).lower()
        if module_slug:
            params["module_slug"] = module_slug
        return self._request("GET", "/api/hosting/tools/", params=params)

    def list_applications(
        self,
        *,
        enabled: bool | None = None,
        module_slug: str | None = None,
    ) -> Any:
        params: dict[str, Any] = {}
        if enabled is not None:
            params["enabled"] = str(enabled).lower()
        if module_slug:
            params["module_slug"] = module_slug
        return self._request("GET", "/api/hosting/applications/", params=params)
