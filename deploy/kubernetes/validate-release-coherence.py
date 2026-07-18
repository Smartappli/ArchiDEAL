#!/usr/bin/env python3
"""Prove that every serving controller and Ready pod uses one release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

import yaml


RELEASE = re.compile(r"^[a-z0-9](?:[-a-z0-9]{0,37}[a-z0-9])?$")
EXPECTED_CONTROLLERS = {
    "dealhost": "Deployment",
    "dealdata-core": "Deployment",
    "dealdata-gps": "Deployment",
    "dealdata-sensor": "Deployment",
    "dealiot-console": "Deployment",
    "mqtt-kafka-bridge": "StatefulSet",
    "dealdata-gps-consumer": "Deployment",
    "dealdata-sensor-consumer": "Deployment",
    "dealinterface": "Deployment",
    "apisix": "Deployment",
    "oauth2-proxy": "Deployment",
}

# This is deliberately explicit: a serving controller may reuse an image, but
# every production image key must be represented by at least one live Pod.
EXPECTED_IMAGE_KEYS = {
    "IMAGE_APISIX",
    "IMAGE_OAUTH2_PROXY",
    "IMAGE_APISIX_BOOTSTRAP",
    "IMAGE_MQTT_KAFKA_BRIDGE",
    "IMAGE_DEALIOT_CONSOLE",
    "IMAGE_DEALHOST",
    "IMAGE_DEALDATA_CORE",
    "IMAGE_DEALDATA_GPS",
    "IMAGE_DEALDATA_SENSOR",
    "IMAGE_DEALINTERFACE",
}
EXPECTED_CONTROLLER_IMAGES = {
    "dealhost": {
        "containers": {"dealhost": "IMAGE_DEALHOST"},
        "initContainers": {},
    },
    "dealdata-core": {
        "containers": {
            "dealdata-core": "IMAGE_DEALDATA_CORE",
            "metrics-proxy": "IMAGE_DEALDATA_CORE",
        },
        "initContainers": {},
    },
    "dealdata-gps": {
        "containers": {
            "dealdata-gps": "IMAGE_DEALDATA_GPS",
            "metrics-proxy": "IMAGE_DEALDATA_GPS",
        },
        "initContainers": {},
    },
    "dealdata-sensor": {
        "containers": {
            "dealdata-sensor": "IMAGE_DEALDATA_SENSOR",
            "metrics-proxy": "IMAGE_DEALDATA_SENSOR",
        },
        "initContainers": {},
    },
    "dealiot-console": {
        "containers": {"dealiot-console": "IMAGE_DEALIOT_CONSOLE"},
        "initContainers": {},
    },
    "mqtt-kafka-bridge": {
        "containers": {"bridge": "IMAGE_MQTT_KAFKA_BRIDGE"},
        "initContainers": {},
    },
    "dealdata-gps-consumer": {
        "containers": {"consumer": "IMAGE_DEALDATA_GPS"},
        "initContainers": {},
    },
    "dealdata-sensor-consumer": {
        "containers": {"consumer": "IMAGE_DEALDATA_SENSOR"},
        "initContainers": {},
    },
    "dealinterface": {
        "containers": {"dealinterface": "IMAGE_DEALINTERFACE"},
        "initContainers": {},
    },
    "apisix": {
        "containers": {
            "apisix": "IMAGE_APISIX",
            # The continuously Ready health sidecar covers the same trusted
            # image used by the invocation-scoped APISIX bootstrap Job.
            "apisix-health": "IMAGE_APISIX_BOOTSTRAP",
        },
        "initContainers": {"prepare-runtime": "IMAGE_APISIX"},
    },
    "oauth2-proxy": {
        "containers": {"oauth2-proxy": "IMAGE_OAUTH2_PROXY"},
        "initContainers": {"validate-valkey-tls": "IMAGE_DEALHOST"},
    },
}


def _positive_integer(value: object, description: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{description} must be a positive integer")
    return value


def _is_ready(pod: dict) -> bool:
    return (
        pod.get("metadata", {}).get("deletionTimestamp") is None
        and pod.get("status", {}).get("phase") == "Running"
        and any(
            condition.get("type") == "Ready"
            and condition.get("status") == "True"
            for condition in pod.get("status", {}).get("conditions", [])
        )
    )


def _container_images(pod_spec: dict, field: str, description: str) -> dict[str, str]:
    containers = pod_spec.get(field, [])
    if not isinstance(containers, list):
        raise ValueError(f"{description} {field} must be a list")
    images: dict[str, str] = {}
    for container in containers:
        if not isinstance(container, dict):
            raise ValueError(f"{description} has a malformed {field} entry")
        name = container.get("name")
        image = container.get("image")
        if not isinstance(name, str) or not name:
            raise ValueError(f"{description} has an unnamed {field} entry")
        if name in images:
            raise ValueError(f"{description} has duplicate {field} entry {name}")
        if not isinstance(image, str) or not image:
            raise ValueError(f"{description} {field} {name} has no image")
        images[name] = image
    return images


def _validate_pod_spec_images(
    pod_spec: dict,
    *,
    controller_name: str,
    description: str,
    image_values: dict,
) -> None:
    if not isinstance(pod_spec, dict):
        raise ValueError(f"{description} has no Pod spec")
    expected_sections = EXPECTED_CONTROLLER_IMAGES[controller_name]
    for field in ("initContainers", "containers"):
        actual = _container_images(pod_spec, field, description)
        expected = expected_sections[field]
        if set(actual) != set(expected):
            raise ValueError(
                f"{description} {field} do not match the production image contract"
            )
        for container_name, values_key in expected.items():
            expected_image = image_values.get(values_key)
            if not isinstance(expected_image, str) or not expected_image:
                raise ValueError(f"values file has no valid {values_key}")
            if actual[container_name] != expected_image:
                raise ValueError(
                    f"{description} {field} {container_name} image does not match "
                    f"{values_key}"
                )


def validate_controller_images(
    controllers_payload: dict,
    pods_payload: dict,
    image_values: dict,
) -> None:
    """Bind controller templates and every Ready serving Pod to ten image values."""
    if not isinstance(image_values, dict):
        raise ValueError("image values must be a YAML mapping")
    mapped_keys = {
        values_key
        for sections in EXPECTED_CONTROLLER_IMAGES.values()
        for mapping in sections.values()
        for values_key in mapping.values()
    }
    if mapped_keys != EXPECTED_IMAGE_KEYS:
        raise RuntimeError("internal controller image map does not cover ten image keys")

    controllers: dict[str, dict] = {}
    for controller in controllers_payload.get("items", []):
        if not isinstance(controller, dict):
            continue
        name = controller.get("metadata", {}).get("name")
        if name in EXPECTED_CONTROLLER_IMAGES:
            if name in controllers:
                raise ValueError(f"duplicate controller snapshot: {name}")
            controllers[name] = controller
    missing = sorted(set(EXPECTED_CONTROLLER_IMAGES) - set(controllers))
    if missing:
        raise ValueError(f"missing production controllers: {', '.join(missing)}")

    for name, controller in controllers.items():
        _validate_pod_spec_images(
            controller.get("spec", {}).get("template", {}).get("spec"),
            controller_name=name,
            description=f"{name} controller template",
            image_values=image_values,
        )

    for pod in pods_payload.get("items", []):
        if not isinstance(pod, dict) or not _is_ready(pod):
            continue
        metadata = pod.get("metadata", {})
        name = metadata.get("labels", {}).get("app.kubernetes.io/name")
        if name not in EXPECTED_CONTROLLER_IMAGES:
            continue
        pod_name = metadata.get("name", "unnamed Pod")
        _validate_pod_spec_images(
            pod.get("spec"),
            controller_name=name,
            description=f"Ready Pod {pod_name}",
            image_values=image_values,
        )


def validate_promoted_ingress(
    ingress: dict,
    *,
    expected_release: str,
    expected_host: str,
) -> None:
    """Require an unfenced Ingress that records one succeeded promotion."""
    if not isinstance(ingress, dict) or ingress.get("kind") != "Ingress":
        raise ValueError("Ingress snapshot must contain one Ingress object")
    metadata = ingress.get("metadata", {})
    if metadata.get("name") != "archideal":
        raise ValueError("Ingress snapshot is not ingress/archideal")
    if metadata.get("deletionTimestamp") is not None:
        raise ValueError("ingress/archideal is terminating")
    annotations = metadata.get("annotations", {})
    if metadata.get("labels", {}).get("archideal.io/release") != expected_release:
        raise ValueError("Ingress label does not match the expected release")
    expected_annotations = {
        "archideal.io/release": expected_release,
        "archideal.io/promotion-state": "succeeded",
        "archideal.io/promotion-release": expected_release,
        "archideal.io/active-release": expected_release,
    }
    for name, value in expected_annotations.items():
        if annotations.get(name) != value:
            raise ValueError(f"Ingress annotation {name} must be {value}")

    rules = ingress.get("spec", {}).get("rules", [])
    rule_hosts = {
        rule.get("host") for rule in rules if isinstance(rule, dict) and rule.get("host")
    }
    tls_hosts = {
        host
        for tls in ingress.get("spec", {}).get("tls", [])
        if isinstance(tls, dict)
        for host in tls.get("hosts", [])
        if isinstance(host, str)
    }
    if rule_hosts != {expected_host} or expected_host not in tls_hosts:
        raise ValueError("Ingress rule and TLS hosts do not match the values file")


def validate_release_coherence(
    controllers_payload: dict,
    pods_payload: dict,
    *,
    expected_release: str | None = None,
    image_values: dict | None = None,
) -> str:
    """Return the unanimous release after checking rollout and serving-pod state."""
    if not isinstance(controllers_payload, dict) or not isinstance(pods_payload, dict):
        raise ValueError("Kubernetes snapshots must be JSON objects")
    controller_items = controllers_payload.get("items")
    pod_items = pods_payload.get("items")
    if not isinstance(controller_items, list) or not isinstance(pod_items, list):
        raise ValueError("Kubernetes snapshots must contain item lists")

    controllers: dict[str, dict] = {}
    for controller in controller_items:
        if not isinstance(controller, dict):
            continue
        name = controller.get("metadata", {}).get("name")
        if name not in EXPECTED_CONTROLLERS:
            continue
        if name in controllers:
            raise ValueError(f"duplicate controller snapshot: {name}")
        controllers[name] = controller
    missing = sorted(set(EXPECTED_CONTROLLERS) - set(controllers))
    if missing:
        raise ValueError(f"missing production controllers: {', '.join(missing)}")

    releases: set[str] = set()
    desired_by_name: dict[str, int] = {}
    for name, expected_kind in EXPECTED_CONTROLLERS.items():
        controller = controllers[name]
        kind = controller.get("kind")
        if kind != expected_kind:
            raise ValueError(f"{name} must be a {expected_kind}, found {kind!r}")
        metadata = controller.get("metadata", {})
        spec = controller.get("spec", {})
        status = controller.get("status", {})
        generation = _positive_integer(metadata.get("generation"), f"{name} generation")
        if status.get("observedGeneration") != generation:
            raise ValueError(f"{name} controller generation is not fully observed")
        desired = _positive_integer(spec.get("replicas"), f"{name} desired replicas")
        desired_by_name[name] = desired
        release = (
            spec.get("template", {})
            .get("metadata", {})
            .get("annotations", {})
            .get("archideal.io/release")
        )
        if (
            not isinstance(release, str)
            or release in {"none", "pending"}
            or not RELEASE.fullmatch(release)
        ):
            raise ValueError(f"{name} has no valid archideal.io/release annotation")
        releases.add(release)

        common_counts = ("readyReplicas", "updatedReplicas")
        if any(status.get(field, 0) != desired for field in common_counts):
            raise ValueError(f"{name} is not fully Ready and updated")
        if kind == "Deployment":
            if (
                status.get("availableReplicas", 0) != desired
                or status.get("unavailableReplicas", 0) != 0
            ):
                raise ValueError(f"{name} Deployment is not fully available")
        elif (
            status.get("currentReplicas", 0) != desired
            or not status.get("currentRevision")
            or status.get("currentRevision") != status.get("updateRevision")
        ):
            raise ValueError(f"{name} StatefulSet has not converged to one revision")

    if len(releases) != 1:
        raise ValueError("production controller templates serve mixed releases")
    release = next(iter(releases))
    if expected_release is not None and release != expected_release:
        raise ValueError(
            f"controllers serve {release}, expected promoted release {expected_release}"
        )

    ready_pods: dict[str, list[dict]] = {name: [] for name in EXPECTED_CONTROLLERS}
    for pod in pod_items:
        if not isinstance(pod, dict) or not _is_ready(pod):
            continue
        name = (
            pod.get("metadata", {})
            .get("labels", {})
            .get("app.kubernetes.io/name")
        )
        if name in ready_pods:
            ready_pods[name].append(pod)
    for name, desired in desired_by_name.items():
        pods = ready_pods[name]
        if len(pods) < desired:
            raise ValueError(
                f"{name} has {len(pods)} Ready serving pods, expected at least {desired}"
            )
        pod_releases = {
            pod.get("metadata", {})
            .get("annotations", {})
            .get("archideal.io/release")
            for pod in pods
        }
        if pod_releases != {release}:
            raise ValueError(f"{name} has Ready pods from mixed releases")
    if image_values is not None:
        validate_controller_images(
            controllers_payload,
            pods_payload,
            image_values,
        )
    return release


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--controllers", required=True, type=Path)
    parser.add_argument("--pods", required=True, type=Path)
    parser.add_argument("--expected-release")
    parser.add_argument("--values", type=Path)
    parser.add_argument("--ingress", type=Path)
    parser.add_argument("--expected-host")
    args = parser.parse_args()
    try:
        if (args.ingress is None) != (args.expected_host is None):
            raise ValueError("--ingress and --expected-host must be used together")
        if args.ingress is not None and args.expected_release is None:
            raise ValueError("--ingress requires --expected-release")
        image_values = (
            yaml.safe_load(args.values.read_text(encoding="utf-8"))
            if args.values is not None
            else None
        )
        release = validate_release_coherence(
            json.loads(args.controllers.read_text(encoding="utf-8")),
            json.loads(args.pods.read_text(encoding="utf-8")),
            expected_release=args.expected_release,
            image_values=image_values,
        )
        if args.ingress is not None:
            validate_promoted_ingress(
                json.loads(args.ingress.read_text(encoding="utf-8")),
                expected_release=args.expected_release,
                expected_host=args.expected_host,
            )
    except (
        OSError,
        RuntimeError,
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        yaml.YAMLError,
    ) as exc:
        parser.error(str(exc))
    print(release)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
