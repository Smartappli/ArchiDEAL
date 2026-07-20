from __future__ import annotations

import hashlib
from typing import Any

from .config import ControllerSettings
from .contract import Component, DesiredDeployment, canonical_json, payload_digest


MANAGED_BY = "dealhost-runtime-controller"
DEPLOYMENT_LABEL = "archideal.io/runtime-deployment"
COMPONENT_LABEL = "archideal.io/runtime-component"
ENVIRONMENT_LABEL = "archideal.io/runtime-environment"


def state_name(deployment_id: str) -> str:
    return f"dealrt-{hashlib.sha256(deployment_id.encode()).hexdigest()[:24]}-state"


def component_name(deployment_id: str, slug: str, *, suffix: str = "") -> str:
    identity = hashlib.sha256(deployment_id.encode()).hexdigest()[:20]
    slug_hash = hashlib.sha256(slug.encode()).hexdigest()[:8]
    reserved = len("dealrt---") + len(identity) + len(slug_hash) + len(suffix)
    available = 63 - reserved
    trimmed = slug[:available].rstrip("-")
    return f"dealrt-{identity}-{trimmed}-{slug_hash}{suffix}"


def resolved_secret_name(settings: ControllerSettings, logical_name: str) -> str:
    """Resolve an opaque control-plane reference without accepting Kubernetes names."""

    return f"{settings.secret_name_prefix}-{logical_name}"


def selector(deployment_id: str, component: str | None = None) -> str:
    values = [
        f"app.kubernetes.io/managed-by={MANAGED_BY}",
        f"{DEPLOYMENT_LABEL}={deployment_id}",
    ]
    if component:
        values.append(f"{COMPONENT_LABEL}={component}")
    return ",".join(values)


def common_labels(
    desired: DesiredDeployment,
    component: Component | None = None,
) -> dict[str, str]:
    labels = {
        "app.kubernetes.io/managed-by": MANAGED_BY,
        "app.kubernetes.io/part-of": "archideal-runtime",
        DEPLOYMENT_LABEL: desired.deployment_id,
        ENVIRONMENT_LABEL: desired.environment,
    }
    if component is not None:
        labels["app.kubernetes.io/name"] = component.slug
        labels[COMPONENT_LABEL] = component.slug
    return labels


def state_config_map(
    desired: DesiredDeployment,
    settings: ControllerSettings,
    *,
    phase: str,
    request_id: str,
) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": state_name(desired.deployment_id),
            "namespace": settings.namespace,
            "labels": common_labels(desired),
            "annotations": {
                "archideal.io/desired-generation": str(desired.generation),
                "archideal.io/release-digest": desired.release_digest,
                "archideal.io/last-request-id": request_id,
                "archideal.io/payload-digest": payload_digest(
                    desired.normalized_payload
                ),
            },
        },
        "data": {
            "phase": phase,
            "desired.json": canonical_json(desired.normalized_payload).decode("utf-8"),
        },
    }


def component_config_map(
    desired: DesiredDeployment,
    component: Component,
    settings: ControllerSettings,
) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": component_name(
                desired.deployment_id, component.slug, suffix="-cfg"
            ),
            "namespace": settings.namespace,
            "labels": common_labels(desired, component),
        },
        "immutable": False,
        "data": dict(sorted(component.configuration.items())),
    }


def deployment_resource(
    desired: DesiredDeployment,
    component: Component,
    settings: ControllerSettings,
    *,
    restart_request: str = "",
) -> dict[str, Any]:
    name = component_name(desired.deployment_id, component.slug)
    labels = common_labels(desired, component)
    pod_labels = {
        **labels,
        "archideal.io/runtime-workload": name,
    }
    scaling = component.scaling
    replicas = 0
    if desired.desired_state == "running":
        replicas = int(
            scaling["replicas"]
            if scaling["mode"] == "fixed"
            else scaling["min_replicas"]
        )
    annotations = {
        "archideal.io/desired-generation": str(desired.generation),
        "archideal.io/release-digest": desired.release_digest,
    }
    if restart_request:
        annotations["archideal.io/restart-request"] = restart_request

    env: list[dict[str, Any]] = []
    config_name = component_name(desired.deployment_id, component.slug, suffix="-cfg")
    for key in sorted(component.configuration):
        env.append(
            {
                "name": key,
                "valueFrom": {"configMapKeyRef": {"name": config_name, "key": key}},
            }
        )
    for key, secret_name in sorted(component.secret_refs.items()):
        env.append(
            {
                "name": key,
                "valueFrom": {
                    "secretKeyRef": {
                        "name": resolved_secret_name(settings, secret_name),
                        "key": key,
                    }
                },
            }
        )

    pod_spec: dict[str, Any] = {
        "serviceAccountName": settings.workload_service_account,
        "automountServiceAccountToken": False,
        "terminationGracePeriodSeconds": 30,
        "securityContext": {
            "runAsNonRoot": True,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "containers": [
            {
                "name": "main",
                "image": component.image,
                "imagePullPolicy": "IfNotPresent",
                "ports": [{"name": "http", "containerPort": component.container_port}],
                "env": env,
                "resources": component.resources,
                "startupProbe": {
                    "httpGet": {"path": component.healthcheck_path, "port": "http"},
                    "periodSeconds": 5,
                    "timeoutSeconds": 2,
                    "failureThreshold": 30,
                },
                "readinessProbe": {
                    "httpGet": {"path": component.healthcheck_path, "port": "http"},
                    "initialDelaySeconds": 2,
                    "periodSeconds": 5,
                    "timeoutSeconds": 2,
                    "failureThreshold": 6,
                },
                "livenessProbe": {
                    "httpGet": {"path": component.healthcheck_path, "port": "http"},
                    "initialDelaySeconds": 10,
                    "periodSeconds": 10,
                    "timeoutSeconds": 2,
                    "failureThreshold": 6,
                },
                "securityContext": {
                    "allowPrivilegeEscalation": False,
                    "readOnlyRootFilesystem": True,
                    "capabilities": {"drop": ["ALL"]},
                },
                "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}],
            }
        ],
        "volumes": [{"name": "tmp", "emptyDir": {}}],
    }
    if settings.image_pull_secret:
        pod_spec["imagePullSecrets"] = [{"name": settings.image_pull_secret}]

    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": name,
            "namespace": settings.namespace,
            "labels": labels,
            "annotations": annotations,
        },
        "spec": {
            "replicas": replicas,
            "revisionHistoryLimit": 3,
            "progressDeadlineSeconds": 600,
            "strategy": {
                "type": "RollingUpdate",
                "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1},
            },
            "selector": {"matchLabels": pod_labels},
            "template": {
                "metadata": {"labels": pod_labels, "annotations": annotations},
                "spec": pod_spec,
            },
        },
    }


def service_resource(
    desired: DesiredDeployment,
    component: Component,
    settings: ControllerSettings,
) -> dict[str, Any]:
    name = component_name(desired.deployment_id, component.slug)
    labels = common_labels(desired, component)
    selector_labels = {
        **labels,
        "archideal.io/runtime-workload": name,
    }
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": name,
            "namespace": settings.namespace,
            "labels": labels,
        },
        "spec": {
            "type": "ClusterIP",
            "selector": selector_labels,
            "ports": [
                {
                    "name": "http",
                    "port": 80,
                    "protocol": "TCP",
                    "targetPort": "http",
                }
            ],
        },
    }


def hpa_resource(
    desired: DesiredDeployment,
    component: Component,
    settings: ControllerSettings,
) -> dict[str, Any]:
    name = component_name(desired.deployment_id, component.slug)
    scaling = component.scaling
    if scaling["mode"] != "autoscale":
        raise ValueError("HPA requested for a fixed-scale component.")
    return {
        "apiVersion": "autoscaling/v2",
        "kind": "HorizontalPodAutoscaler",
        "metadata": {
            "name": name,
            "namespace": settings.namespace,
            "labels": common_labels(desired, component),
        },
        "spec": {
            "scaleTargetRef": {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "name": name,
            },
            "minReplicas": scaling["min_replicas"],
            "maxReplicas": scaling["max_replicas"],
            "metrics": [
                {
                    "type": "Resource",
                    "resource": {
                        "name": "cpu",
                        "target": {
                            "type": "Utilization",
                            "averageUtilization": scaling["target_cpu_utilization"],
                        },
                    },
                }
            ],
            "behavior": {
                "scaleDown": {"stabilizationWindowSeconds": 300},
                "scaleUp": {"stabilizationWindowSeconds": 0},
            },
        },
    }
