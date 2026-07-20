from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import httpx

from .config import ControllerSettings


MAX_KUBERNETES_RESPONSE_BYTES = 2 * 1024 * 1024

_RESOURCE_ENDPOINTS = {
    "ConfigMap": ("/api/v1", "configmaps"),
    "Service": ("/api/v1", "services"),
    "Pod": ("/api/v1", "pods"),
    "Deployment": ("/apis/apps/v1", "deployments"),
    "HorizontalPodAutoscaler": (
        "/apis/autoscaling/v2",
        "horizontalpodautoscalers",
    ),
}


class KubernetesApiError(RuntimeError):
    def __init__(self, detail: str, *, status_code: int | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code


class KubernetesClient:
    """Minimal namespace-bound Kubernetes REST client using projected credentials."""

    def __init__(
        self,
        settings: ControllerSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self.transport = transport

    async def apply(self, resource: dict[str, Any]) -> dict[str, Any]:
        kind = resource.get("kind")
        metadata = resource.get("metadata")
        if kind not in _RESOURCE_ENDPOINTS or not isinstance(metadata, dict):
            raise ValueError("Unsupported Kubernetes resource.")
        name = metadata.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("Kubernetes resource name is required.")
        prefix, plural = _RESOURCE_ENDPOINTS[kind]
        return await self._request_json(
            "PATCH",
            self._resource_path(prefix, plural, name),
            params={"fieldManager": "dealhost-runtime-controller", "force": "true"},
            content=json.dumps(
                resource,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
            content_type="application/apply-patch+yaml",
            expected={200, 201},
        )

    async def get(
        self,
        kind: str,
        name: str,
        *,
        namespace: str | None = None,
    ) -> dict[str, Any] | None:
        prefix, plural = self._endpoint(kind)
        response = await self._request(
            "GET",
            self._resource_path(prefix, plural, name, namespace=namespace),
            expected={200, 404},
        )
        if response.status_code == 404:
            return None
        return self._json(response)

    async def list(
        self,
        kind: str,
        *,
        label_selector: str,
    ) -> list[dict[str, Any]]:
        prefix, plural = self._endpoint(kind)
        response = await self._request(
            "GET",
            self._resource_path(prefix, plural),
            params={"labelSelector": label_selector, "limit": "500"},
            expected={200},
        )
        payload = self._json(response)
        items = payload.get("items")
        if not isinstance(items, list) or any(
            not isinstance(item, dict) for item in items
        ):
            raise KubernetesApiError("Kubernetes returned an invalid resource list.")
        if payload.get("metadata", {}).get("continue"):
            raise KubernetesApiError(
                "Kubernetes returned more runtime resources than the safety limit."
            )
        return items

    async def delete(self, kind: str, name: str) -> None:
        prefix, plural = self._endpoint(kind)
        await self._request(
            "DELETE",
            self._resource_path(prefix, plural, name),
            content=b'{"apiVersion":"v1","kind":"DeleteOptions","propagationPolicy":"Foreground"}',
            content_type="application/json",
            expected={200, 202, 404},
        )

    async def pod_logs(
        self,
        pod_name: str,
        *,
        container: str,
        tail_lines: int,
        since_seconds: int,
    ) -> str:
        prefix, plural = self._endpoint("Pod")
        response = await self._request(
            "GET",
            f"{self._resource_path(prefix, plural, pod_name)}/log",
            params={
                "container": container,
                "tailLines": str(tail_lines),
                "sinceSeconds": str(since_seconds),
                "timestamps": "true",
                "limitBytes": "1000000",
            },
            expected={200},
        )
        content_type = response.headers.get("content-type", "").split(";", 1)[0]
        if content_type not in {"text/plain", "application/octet-stream", ""}:
            raise KubernetesApiError("Kubernetes returned an invalid log response.")
        return response.text

    async def ready(self) -> None:
        """Exercise the mounted token and namespace-scoped RBAC."""

        prefix, plural = self._endpoint("ConfigMap")
        payload = await self._request_json(
            "GET",
            self._resource_path(prefix, plural),
            params={"limit": "1"},
            expected={200},
        )
        if not isinstance(payload.get("items"), list):
            raise KubernetesApiError(
                "Kubernetes returned an invalid readiness response."
            )

    def _endpoint(self, kind: str) -> tuple[str, str]:
        try:
            return _RESOURCE_ENDPOINTS[kind]
        except KeyError as exc:
            raise ValueError(f"Unsupported Kubernetes kind: {kind}") from exc

    def _resource_path(
        self,
        prefix: str,
        plural: str,
        name: str = "",
        *,
        namespace: str | None = None,
    ) -> str:
        resource_namespace = namespace or self.settings.namespace
        base = (
            f"{prefix}/namespaces/{quote(resource_namespace, safe='')}/"
            f"{quote(plural, safe='')}"
        )
        return f"{base}/{quote(name, safe='')}" if name else base

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        expected: set[int],
        params: dict[str, str] | None = None,
        content: bytes | None = None,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        response = await self._request(
            method,
            path,
            expected=expected,
            params=params,
            content=content,
            content_type=content_type,
        )
        return self._json(response)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        expected: set[int],
        params: dict[str, str] | None = None,
        content: bytes | None = None,
        content_type: str | None = None,
    ) -> httpx.Response:
        try:
            token = self.settings.kubernetes_token_file.read_text(
                encoding="utf-8"
            ).strip()
        except OSError as exc:
            raise KubernetesApiError(
                "The projected Kubernetes credential is unavailable."
            ) from exc
        if not token:
            raise KubernetesApiError("The projected Kubernetes credential is empty.")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        if content_type:
            headers["Content-Type"] = content_type
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.kubernetes_url,
                verify=str(self.settings.kubernetes_ca_file),
                timeout=self.settings.request_timeout_seconds,
                follow_redirects=False,
                trust_env=False,
                transport=self.transport,
            ) as client:
                response = await client.request(
                    method,
                    path,
                    headers=headers,
                    params=params,
                    content=content,
                )
        except httpx.HTTPError as exc:
            raise KubernetesApiError(
                "The Kubernetes API could not be reached."
            ) from exc
        if len(response.content) > MAX_KUBERNETES_RESPONSE_BYTES:
            raise KubernetesApiError("The Kubernetes API response is too large.")
        if response.status_code not in expected:
            raise KubernetesApiError(
                f"The Kubernetes API rejected {method} {path} (HTTP {response.status_code}).",
                status_code=response.status_code,
            )
        return response

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "").split(";", 1)[0]
        if content_type != "application/json":
            raise KubernetesApiError("Kubernetes returned a non-JSON response.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise KubernetesApiError("Kubernetes returned malformed JSON.") from exc
        if not isinstance(payload, dict):
            raise KubernetesApiError("Kubernetes returned an invalid response.")
        return payload
