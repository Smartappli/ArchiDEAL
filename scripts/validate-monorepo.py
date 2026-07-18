"""Fail fast when a cross-component ArchiDEAL contract drifts."""

from __future__ import annotations

import json
from pathlib import Path
import sys

try:
    import yaml
except ImportError as exc:  # pragma: no cover - developer setup guard
    raise SystemExit("PyYAML is required: python -m pip install PyYAML") from exc


ROOT = Path(__file__).resolve().parent.parent
EXPECTED_COMPONENTS = {"DEALIoT", "DEALHost", "DEALData", "DEALInterface"}
EXPECTED_PREFIXES = {
    "/dealhost": "dealhost:8000",
    "/dealiot": "dealiot:8080",
    "/dealdata/core": "dealdata-core:7000",
    "/dealdata/gps": "dealdata-gps:7001",
    "/dealdata/sensor": "dealdata-sensor:7002",
}


def fail(message: str) -> None:
    raise AssertionError(message)


def networks(service: dict) -> set[str]:
    configured = service.get("networks", [])
    if isinstance(configured, dict):
        return set(configured)
    return set(configured)


def volume_targets(service: dict) -> set[str]:
    targets = set()
    for volume in service.get("volumes", []):
        if isinstance(volume, dict):
            target = volume.get("target")
        else:
            parts = str(volume).split(":")
            target = parts[1] if len(parts) > 1 else parts[0]
        if target:
            targets.add(target)
    return targets


def reject_legacy_postgres_18_mounts(path: Path) -> None:
    compose = yaml.safe_load(path.read_text(encoding="utf-8"))
    for service_name, service in compose.get("services", {}).items():
        if str(service.get("image", "")).startswith("postgres:18"):
            if "/var/lib/postgresql/data" in volume_targets(service):
                fail(f"{path}: {service_name} uses the pre-PostgreSQL 18 data mount")


def validate_sources() -> None:
    lock = json.loads((ROOT / "sources.lock.json").read_text(encoding="utf-8"))
    components = lock.get("components", {})
    if set(components) != EXPECTED_COMPONENTS:
        fail(f"unexpected source set: {sorted(components)}")
    if lock.get("history_mode") != "snapshot":
        fail("the import history mode must remain explicit")
    if "https://github.com/Smartappli/DEALWebsite" not in lock.get(
        "excluded_repositories", [],
    ):
        fail("DEALWebsite exclusion is not recorded")

    for name, metadata in components.items():
        path = ROOT / metadata["path"]
        if not path.is_dir():
            fail(f"missing component directory: {path}")
        if (path / ".git").exists():
            fail(f"nested Git repository is forbidden: {path}")
        for required in ("README.md", "LICENSE"):
            if not (path / required).is_file():
                fail(f"{name} is missing {required}")
        for field in ("commit", "tree"):
            value = metadata.get(field, "")
            if len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
                fail(f"invalid {name} {field} SHA")

    if (ROOT / "components" / "DEALWebsite").exists():
        fail("DEALWebsite must not be imported into ArchiDEAL")


def validate_compose() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    services = compose["services"]
    required = {
        "kafka",
        "kafka-init",
        "vernemq",
        "mqtt-kafka-bridge",
        "dealdata-core",
        "dealdata-gps",
        "dealdata-sensor",
        "dealdata-gps-consumer",
        "dealdata-sensor-consumer",
        "dealhost",
        "dealiot",
        "dealinterface",
        "apisix-etcd",
        "apisix",
        "apisix-bootstrap",
    }
    missing = required - set(services)
    if missing:
        fail(f"missing integration services: {sorted(missing)}")

    reject_legacy_postgres_18_mounts(ROOT / "compose.yaml")
    for service_name in (
        "dealdata-core-db",
        "dealdata-gps-db",
        "dealdata-sensor-db",
    ):
        if "/var/lib/postgresql" not in volume_targets(services[service_name]):
            fail(f"{service_name} must persist the PostgreSQL 18 cluster root")

    published = {name for name, service in services.items() if service.get("ports")}
    if published != {"apisix"}:
        fail(f"only APISIX may publish host ports, found: {sorted(published)}")
    apisix_port = str(services["apisix"]["ports"][0])
    if not apisix_port.startswith("127.0.0.1:") or not apisix_port.endswith(":9080"):
        fail("APISIX must bind its data-plane port to host loopback")

    expected_networks = {
        "mqtt-kafka-bridge": {"ingest", "event", "api"},
        "dealdata-gps-consumer": {"data", "event"},
        "dealdata-sensor-consumer": {"data", "event"},
        "dealhost": {"host", "api"},
        "dealiot": {"api", "event", "ingest"},
        "dealinterface": {"edge"},
        "apisix": {"edge", "api", "host"},
    }
    for service_name, expected in expected_networks.items():
        actual = networks(services[service_name])
        if actual != expected:
            fail(f"{service_name} networks {sorted(actual)} != {sorted(expected)}")

    event_env = services["dealdata-gps-consumer"]["environment"]
    if event_env.get("DEALDATA_KAFKA_BOOTSTRAP_SERVERS") != "kafka:9092":
        fail("DEALData consumers must use the root Kafka DNS name")
    if event_env.get("DEALDATA_GPS_KAFKA_TOPIC") != "raw.gps":
        fail("GPS topic contract drifted")
    sensor_env = services["dealdata-sensor-consumer"]["environment"]
    if sensor_env.get("DEALDATA_SENSOR_KAFKA_TOPIC") != "raw.sensor":
        fail("Sensor topic contract drifted")

    # This root stack is intentionally HTTP-only development infrastructure.
    # DEALData entrypoints run `check --deploy` when DEBUG is false, which would
    # correctly reject the disabled SSL redirect and stop every API/consumer.
    for service_name in (
        "dealdata-core",
        "dealdata-gps",
        "dealdata-sensor",
        "dealdata-gps-consumer",
        "dealdata-sensor-consumer",
    ):
        environment = services[service_name]["environment"]
        if str(environment.get("DJANGO_DEBUG", "")).casefold() != "true":
            fail(f"{service_name} must remain in development mode in root Compose")

    bridge_health = services["mqtt-kafka-bridge"]["healthcheck"]["test"]
    if not any("/readyz" in str(part) for part in bridge_health):
        fail("the Rust MQTT bridge readiness probe must check /readyz")

    host_env = services["dealhost"]["environment"]
    if host_env.get("GITHUB_REPOSITORY") != "ArchiDEAL":
        fail("DEALHost must discover the ArchiDEAL repository")
    if host_env.get("GITHUB_ALLOWED_REPOSITORIES") != "Smartappli/ArchiDEAL":
        fail("DEALHost webhooks must be restricted to Smartappli/ArchiDEAL")


def validate_gateway() -> None:
    config = yaml.safe_load((ROOT / "deploy/apisix/config.yaml").read_text(encoding="utf-8"))
    deployment = config["deployment"]
    if deployment.get("role") != "traditional":
        fail("APISIX must use traditional mode for DEALHost route PUTs")
    if deployment.get("role_traditional", {}).get("config_provider") != "etcd":
        fail("APISIX traditional mode must use etcd")
    if deployment.get("admin", {}).get("admin_listen", {}).get("port") != 9180:
        fail("unexpected APISIX Admin port")

    route_list = json.loads(
        (ROOT / "deploy/apisix/routes.json").read_text(encoding="utf-8"),
    )["routes"]
    routes = {route["uris"][0]: route for route in route_list}
    for prefix, upstream in EXPECTED_PREFIXES.items():
        route = routes.get(prefix)
        if route is None:
            fail(f"missing APISIX route for {prefix}")
        if route.get("uris") != [prefix, f"{prefix}/*"]:
            fail(f"route {prefix} must match exact and wildcard paths")
        rewrite = route.get("plugins", {}).get("proxy-rewrite", {})
        if rewrite.get("regex_uri", [None])[0] != f"^{prefix}/?(.*)$":
            fail(f"route {prefix} does not strip its prefix")
        if upstream not in route.get("upstream", {}).get("nodes", {}):
            fail(f"route {prefix} does not target {upstream}")

    ui = routes.get("/")
    if not ui or ui.get("priority", 0) >= 0:
        fail("the DEALInterface catch-all route must have negative priority")

    host_service = (ROOT / "components/DEALHost/apps/gateway/services.py").read_text(
        encoding="utf-8",
    )
    for token in ('"uris": [public_path, f"{public_path}/*"]', '"proxy-rewrite"'):
        if token not in host_service:
            fail("DEALHost dynamic routes would overwrite the gateway contract")


def validate_component_compatibility() -> None:
    reject_legacy_postgres_18_mounts(ROOT / "components/DEALData/docker-compose.yml")
    reject_legacy_postgres_18_mounts(ROOT / "components/DEALIoT/docker-compose.yml")

    dealhost_dockerignore = (
        ROOT / "components/DEALHost/.dockerignore"
    ).read_text(encoding="utf-8").splitlines()
    for sensitive_pattern in (".env", ".env.*", "secrets/", "*.pem", "*.key"):
        if sensitive_pattern not in dealhost_dockerignore:
            fail(f"DEALHost Docker context must exclude {sensitive_pattern}")

    repository_manifests = sorted(
        (ROOT / "components/DEALHost/manifests/repositories").glob("*.json"),
    )
    if [path.name for path in repository_manifests] != ["archideal.json"]:
        fail("DEALHost must expose one ArchiDEAL repository manifest")
    host_repository = json.loads(repository_manifests[0].read_text(encoding="utf-8"))
    if host_repository.get("repository_full_name") != "Smartappli/ArchiDEAL":
        fail("DEALHost repository manifest still targets a legacy repository")

    pyflink = (ROOT / "components/DEALIoT/flink/requirements-pyflink.txt").read_text(
        encoding="utf-8",
    )
    if "apache-flink==2.2.1" not in pyflink:
        fail("PyFlink must match the Flink 2.2.1 runtime")

    kafka_consumer = (ROOT / "components/DEALData/dealdata_common/kafka.py").read_text(
        encoding="utf-8",
    )
    for token in ("SASL_SSL", "ssl_check_hostname", "sasl_plain_username"):
        if token not in kafka_consumer:
            fail(f"DEALData Kafka security is missing {token}")

    registry = (
        ROOT / "components/DEALInterface/src/config/moduleRegistry.ts"
    ).read_text(encoding="utf-8")
    for prefix in EXPECTED_PREFIXES:
        if prefix.startswith("/dealdata/") or prefix in {"/dealhost", "/dealiot"}:
            if f'"{prefix}"' not in registry:
                fail(f"DEALInterface is missing relative route {prefix}")


def main() -> None:
    validate_sources()
    validate_compose()
    validate_gateway()
    validate_component_compatibility()
    print("ArchiDEAL monorepo contracts are valid.")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        print(f"validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
