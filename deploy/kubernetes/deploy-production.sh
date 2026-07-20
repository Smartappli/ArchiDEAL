#!/usr/bin/env bash
set -Eeuo pipefail

namespace="archideal"
runtime_apps_namespace="archideal-runtime-apps"
timeout="15m"
values_file=""
context=""
smoke_token_file=""
release_manifest=""
release_bundle=""
release_evidence_dir=""
approve_live_upgrade="false"
work_dir=""
mutation_started="false"
promotion_succeeded="false"
previous_release="none"
previous_release_safe="false"
invocation_id="pending"

usage() {
  printf '%s\n' \
    "Usage: $0 --values PATH --context KUBECTL_CONTEXT --smoke-token-file PATH \\" \
    "          --release-manifest PATH --release-bundle PATH \\" \
    "          --release-evidence-dir PATH [OPTIONS]" \
    "" \
    "Options:" \
    "  --timeout DURATION          Readiness timeout (default: 15m)" \
    "  --approve-live-upgrade      Assert migrations are expand/contract compatible" \
    "                              when an ArchiDEAL Ingress already exists" \
    "" \
    "Promotes a digest-pinned ArchiDEAL release in ordered, fail-closed phases."
}

while (($#)); do
  case "$1" in
    --values)
      values_file="${2:-}"
      shift 2
      ;;
    --context)
      context="${2:-}"
      shift 2
      ;;
    --timeout)
      timeout="${2:-}"
      shift 2
      ;;
    --smoke-token-file)
      smoke_token_file="${2:-}"
      shift 2
      ;;
    --release-manifest)
      release_manifest="${2:-}"
      shift 2
      ;;
    --release-bundle)
      release_bundle="${2:-}"
      shift 2
      ;;
    --release-evidence-dir)
      release_evidence_dir="${2:-}"
      shift 2
      ;;
    --approve-live-upgrade)
      approve_live_upgrade="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$values_file" || -z "$context" || -z "$smoke_token_file" || \
      -z "$release_manifest" || -z "$release_bundle" || \
      -z "$release_evidence_dir" ]]; then
  usage >&2
  exit 2
fi
if [[ ! -f "$values_file" ]]; then
  printf 'Values file does not exist: %s\n' "$values_file" >&2
  exit 2
fi
if [[ ! -s "$smoke_token_file" ]]; then
  printf 'Smoke bearer token file does not exist or is empty: %s\n' "$smoke_token_file" >&2
  exit 2
fi
if [[ ! -f "$release_manifest" || ! -f "$release_bundle" || \
      ! -d "$release_evidence_dir" ]]; then
  printf '%s\n' \
    'The release manifest, Sigstore bundle or evidence directory is missing.' >&2
  exit 2
fi
if [[ ! "$timeout" =~ ^[1-9][0-9]*(s|m|h)$ ]]; then
  printf 'Timeout must be a positive kubectl duration (for example 15m).\n' >&2
  exit 2
fi
timeout_value="${timeout%?}"
case "${timeout: -1}" in
  s) timeout_seconds="$((10#$timeout_value))" ;;
  m) timeout_seconds="$((10#$timeout_value * 60))" ;;
  h) timeout_seconds="$((10#$timeout_value * 3600))" ;;
esac

for executable in python git kubectl cosign; do
  if ! command -v "$executable" >/dev/null 2>&1; then
    printf 'Missing required executable: %s\n' "$executable" >&2
    exit 2
  fi
done

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
resolve_path() {
  python -c \
    'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' \
    "$1"
}
read_value() {
  python -c \
    'import sys, yaml; print(yaml.safe_load(open(sys.argv[1], encoding="utf-8"))[sys.argv[2]])' \
    "$values_file" "$1"
}
values_file="$(resolve_path "$values_file")"
smoke_token_file="$(resolve_path "$smoke_token_file")"
release_manifest="$(resolve_path "$release_manifest")"
release_bundle="$(resolve_path "$release_bundle")"
release_evidence_dir="$(resolve_path "$release_evidence_dir")"

printf 'Supply-chain gate: signed release, evidence and image attestations\n'
python "$script_dir/verify-release.py" \
  --values "$values_file" \
  --manifest "$release_manifest" \
  --bundle "$release_bundle" \
  --evidence-dir "$release_evidence_dir"
release_id="$(read_value RELEASE_ID)"
runtime_secret_name="archideal-runtime-secrets-$release_id"
runtime_controller_tls_secret_name="dealhost-runtime-controller-tls-$release_id"
public_host="$(read_value PUBLIC_HOST)"
tls_secret_name="$(read_value TLS_SECRET_NAME)"
ingress_class="$(read_value INGRESS_CLASS)"
ingress_namespace="$(read_value INGRESS_NAMESPACE)"
ingress_proxy_cidr="$(read_value INGRESS_PROXY_CIDR)"
cluster_issuer="$(read_value CLUSTER_ISSUER)"
secret_store_name="$(read_value SECRET_STORE_NAME)"
monitoring_namespace="$(read_value MONITORING_NAMESPACE)"
oidc_issuer_url="$(read_value OIDC_ISSUER_URL)"
oidc_introspection_url="$(read_value OIDC_INTROSPECTION_URL)"
oidc_egress_cidr="$(read_value OIDC_EGRESS_CIDR)"
github_egress_cidr="$(read_value GITHUB_EGRESS_CIDR)"
otel_collector_url="$(read_value OTEL_COLLECTOR_HTTP_ENDPOINT)"
otel_egress_cidr="$(read_value OTEL_EGRESS_CIDR)"
valkey_host="$(read_value VALKEY_HOST)"

controller_order=(
  dealhost-runtime-controller
  dealhost-runtime-worker
  dealhost
  dealdata-core
  dealdata-gps
  dealdata-sensor
  dealiot-console
  mqtt-kafka-bridge
  dealdata-gps-consumer
  dealdata-sensor-consumer
  dealinterface
  apisix
  oauth2-proxy
)

known_context="$(kubectl config get-contexts "$context" -o name 2>/dev/null || true)"
if [[ "$known_context" != "$context" ]]; then
  printf 'kubectl context not found or ambiguous: %s\n' "$context" >&2
  exit 2
fi

required_crds=(
  externalsecrets.external-secrets.io
  clustersecretstores.external-secrets.io
  certificates.cert-manager.io
  clusterissuers.cert-manager.io
  servicemonitors.monitoring.coreos.com
  podmonitors.monitoring.coreos.com
  prometheusrules.monitoring.coreos.com
)
if ! kubectl --context "$context" get crd "${required_crds[@]}" >/dev/null; then
  printf '%s\n' \
    'External Secrets, cert-manager and Prometheus Operator CRDs are required before any production mutation.' >&2
  exit 2
fi
if ! kubectl --context "$context" get \
  "namespace/$ingress_namespace" \
  "namespace/$monitoring_namespace" \
  "ingressclass.networking.k8s.io/$ingress_class" >/dev/null; then
  printf '%s\n' \
    'Ingress/monitoring namespaces and the configured IngressClass must exist before promotion.' >&2
  exit 2
fi
ingress_controller="$(
  kubectl --context "$context" get \
    "ingressclass.networking.k8s.io/$ingress_class" \
    -o jsonpath='{.spec.controller}'
)"
if [[ "$ingress_controller" != "k8s.io/ingress-nginx" ]]; then
  printf '%s\n' \
    'The configured IngressClass must be implemented by k8s.io/ingress-nginx.' >&2
  exit 2
fi
kubectl --context "$context" --namespace "$ingress_namespace" get pods \
  --selector='app.kubernetes.io/name=ingress-nginx,app.kubernetes.io/component=controller' \
  -o json | python "$script_dir/validate-ingress-controller.py" \
    --ingress-class "$ingress_class" \
    --controller-class "$ingress_controller" \
    --proxy-cidr "$ingress_proxy_cidr"

python - \
  "$oidc_egress_cidr" "$oidc_issuer_url" "$oidc_introspection_url" \
  "$github_egress_cidr" "https://api.github.com" \
  "$otel_egress_cidr" "$otel_collector_url" <<'PY'
import ipaddress
import socket
import sys
from urllib.parse import urlsplit

checks = (
    ("OIDC", sys.argv[1], (sys.argv[2], sys.argv[3])),
    ("GitHub", sys.argv[4], (sys.argv[5],)),
    ("OpenTelemetry", sys.argv[6], (sys.argv[7],)),
)
for label, cidr, urls in checks:
    network = ipaddress.ip_network(cidr, strict=True)
    for url in urls:
        host = urlsplit(url).hostname
        if not host:
            raise SystemExit(f"{label} endpoint has no hostname")
        try:
            resolved = {
                ipaddress.ip_address(item[4][0].split("%", 1)[0])
                for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            }
        except socket.gaierror as exc:
            raise SystemExit(f"{label} DNS resolution failed for {host}: {exc}") from exc
        applicable = {address for address in resolved if address.version == network.version}
        if not applicable or any(address not in network for address in applicable):
            raise SystemExit(
                f"{label} DNS addresses for {host} are outside the approved {cidr}"
            )
PY
require_cluster_condition() {
  local reference="$1"
  local condition_type="$2"
  local status
  if ! status="$(
    kubectl --context "$context" get "$reference" \
      -o "jsonpath={.status.conditions[?(@.type==\"$condition_type\")].status}"
  )" || [[ "$status" != "True" ]]; then
    printf 'Required cluster resource is not %s=True: %s\n' \
      "$condition_type" "$reference" >&2
    exit 2
  fi
}
require_cluster_condition \
  "clusterissuer.cert-manager.io/$cluster_issuer" Ready
require_cluster_condition \
  "clustersecretstore.external-secrets.io/$secret_store_name" Ready
require_cluster_condition \
  "apiservice.apiregistration.k8s.io/v1beta1.metrics.k8s.io" Available

eligible_zones="$(
  kubectl --context "$context" get nodes \
    --selector='kubernetes.io/os=linux,kubernetes.io/arch=amd64' \
    -o json | python -c '
import json, sys
nodes = json.load(sys.stdin).get("items", [])
zones = set()
for node in nodes:
    if node.get("spec", {}).get("unschedulable"):
        continue
    conditions = node.get("status", {}).get("conditions", [])
    if not any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in conditions
    ):
        continue
    zone = node.get("metadata", {}).get("labels", {}).get(
        "topology.kubernetes.io/zone",
    )
    if zone:
        zones.add(zone)
print("\n".join(sorted(zones)))
'
)"
mapfile -t production_zones < <(printf '%s\n' "$eligible_zones" | sed '/^$/d')
if ((${#production_zones[@]} < 3)); then
  printf '%s\n' \
    'Production requires Ready, schedulable Linux/amd64 nodes in at least three labelled zones.' >&2
  exit 2
fi

ready_scrapers="$(
  kubectl --context "$context" --namespace "$monitoring_namespace" get pods \
    --selector='monitoring.archideal.io/scraper=true' \
    -o json | python -c '
import json, sys
pods = json.load(sys.stdin).get("items", [])
print(sum(
    1
    for pod in pods
    if any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in pod.get("status", {}).get("conditions", [])
    )
))
'
)"
if [[ ! "$ready_scrapers" =~ ^[1-9][0-9]*$ ]]; then
  printf '%s\n' \
    'Monitoring requires at least one Ready pod labelled monitoring.archideal.io/scraper=true.' >&2
  exit 2
fi

work_dir="$(mktemp -d -t archideal-production.XXXXXXXX)"
kubectl_base=(kubectl --context "$context")
kubectl_ns=(kubectl --context "$context" --namespace "$namespace")
cleanup() {
  if [[ -n "$work_dir" && "$work_dir" == /tmp/archideal-production.* && -d "$work_dir" ]]; then
    rm -rf -- "$work_dir"
  fi
}
print_rollback_command() {
  local rollback_release rollback_root
  rollback_release="$previous_release"
  if [[ "$previous_release_safe" != "true" || "$rollback_release" == "none" ]]; then
    rollback_release="previous-signed-release"
    printf '%s\n' \
      'No validated previous release was available; select a signed, schema-compatible release.' >&2
  fi
  rollback_root="/secure/releases/$rollback_release"
  printf '%s\n' 'Explicit rollback command (never performs a schema downgrade):' >&2
  printf '  make -C %q production-rollback \\\n' "$rollback_root/source" >&2
  printf '    KUBE_CONTEXT=%q \\\n' "$context" >&2
  printf '    ROLLBACK_VALUES=%q \\\n' "$rollback_root/values.yaml" >&2
  printf '    ROLLBACK_RELEASE_MANIFEST=%q \\\n' \
    "$rollback_root/release-manifest.json" >&2
  printf '    ROLLBACK_RELEASE_BUNDLE=%q \\\n' \
    "$rollback_root/release-manifest.sigstore.json" >&2
  printf '    ROLLBACK_RELEASE_EVIDENCE_DIR=%q \\\n' "$rollback_root" >&2
  printf '    ARCHIDEAL_BEARER_TOKEN_FILE=%q \\\n' \
    "$smoke_token_file" >&2
  printf '    APPROVE_SCHEMA_COMPATIBLE_ROLLBACK=1\n' >&2
}
annotate_promotion_state() {
  local state="$1"
  local active_release="none"
  if [[ "$state" == "succeeded" ]]; then
    active_release="$release_id"
  fi
  "${kubectl_base[@]}" annotate "namespace/$namespace" \
    "archideal.io/promotion-state=$state" \
    "archideal.io/promotion-release=$release_id" \
    "archideal.io/active-release=$active_release" \
    "archideal.io/previous-release=$previous_release" \
    "archideal.io/promotion-invocation=$invocation_id" \
    --overwrite >/dev/null
}
fence_failed_promotion() {
  local ingress_reference verify_reference
  printf '%s\n' \
    'Promotion failed after cluster mutation; fencing the public Ingress.' >&2
  if ! ingress_reference="$(
    "${kubectl_ns[@]}" get ingress/archideal --ignore-not-found -o name
  )"; then
    printf '%s\n' \
      'CRITICAL: the Ingress state could not be read during fencing.' >&2
  elif [[ -n "$ingress_reference" ]]; then
    "${kubectl_ns[@]}" delete ingress/archideal \
      --ignore-not-found --wait=false >/dev/null || true
    if ! "${kubectl_ns[@]}" wait \
      --for=delete ingress/archideal --timeout="$timeout" >/dev/null; then
      printf '%s\n' \
        'CRITICAL: Ingress fencing did not complete before the timeout.' >&2
    fi
  fi
  if ! verify_reference="$(
    "${kubectl_ns[@]}" get ingress/archideal --ignore-not-found -o name
  )"; then
    printf '%s\n' \
      'CRITICAL: the Ingress absence could not be verified.' >&2
  elif [[ -n "$verify_reference" ]]; then
    printf '%s\n' \
      'CRITICAL: ingress/archideal still exists; remove it before any recovery.' >&2
  else
    printf '%s\n' 'Public Ingress is absent; the failed promotion is fenced.' >&2
  fi
  if ! annotate_promotion_state failed; then
    printf '%s\n' \
      'WARNING: failed promotion state could not be annotated on the namespace.' >&2
  fi
  print_rollback_command
}
on_exit() {
  local original_status=$?
  trap - EXIT INT TERM
  set +e
  if [[ "$original_status" -ne 0 && "$mutation_started" == "true" && \
        "$promotion_succeeded" != "true" ]]; then
    fence_failed_promotion
  fi
  cleanup
  exit "$original_status"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

active_ingress_json="$work_dir/active-ingress.json"
"${kubectl_ns[@]}" get ingress/archideal \
  --ignore-not-found -o json >"$active_ingress_json"
if [[ -s "$active_ingress_json" ]]; then
  if [[ "$approve_live_upgrade" != "true" ]]; then
    printf '%s\n' \
      'An active ArchiDEAL Ingress already exists.' \
      'Re-run with --approve-live-upgrade only after confirming that every' \
      'migration is backward-compatible (expand/contract) with the active release.' >&2
    exit 2
  fi
  controllers_json="$work_dir/active-controllers.json"
  pods_json="$work_dir/active-pods.json"
  "${kubectl_ns[@]}" get deployments.apps,statefulsets.apps \
    -o json >"$controllers_json"
  "${kubectl_ns[@]}" get pods \
    --selector='app.kubernetes.io/part-of=archideal' -o json >"$pods_json"
  previous_release="$(
    python "$script_dir/validate-release-coherence.py" \
      --controllers "$controllers_json" --pods "$pods_json" \
      --allow-missing-runtime-management
  )"
  ingress_snapshot="$(
    python -c '
import json, sys
ingress = json.load(open(sys.argv[1], encoding="utf-8"))
if ingress.get("metadata", {}).get("deletionTimestamp"):
    raise SystemExit("active Ingress is already terminating")
metadata = ingress.get("metadata", {})
annotations = metadata.get("annotations", {})
print("|".join((
    metadata.get("labels", {}).get("archideal.io/release", ""),
    annotations.get("archideal.io/promotion-state", ""),
    annotations.get("archideal.io/promotion-release", ""),
    annotations.get("archideal.io/active-release", ""),
)))
' "$active_ingress_json"
  )"
  IFS='|' read -r ingress_release ingress_state ingress_promotion ingress_active \
    <<<"$ingress_snapshot"
  active_namespace_json="$work_dir/active-namespace.json"
  "${kubectl_base[@]}" get "namespace/$namespace" -o json >"$active_namespace_json"
  namespace_snapshot="$(
    python -c '
import json, sys
annotations = json.load(open(sys.argv[1], encoding="utf-8")).get("metadata", {}).get("annotations", {})
print("|".join((
    annotations.get("archideal.io/promotion-state", ""),
    annotations.get("archideal.io/promotion-release", ""),
    annotations.get("archideal.io/active-release", ""),
)))
' "$active_namespace_json"
  )"
  IFS='|' read -r namespace_promotion_state namespace_promotion namespace_active \
    <<<"$namespace_snapshot"
  if [[ "$ingress_release" != "$previous_release" || \
        "$ingress_state" != "succeeded" || \
        "$ingress_promotion" != "$previous_release" || \
        "$ingress_active" != "$previous_release" || \
        "$namespace_promotion_state" != "succeeded" || \
        "$namespace_promotion" != "$previous_release" || \
        "$namespace_active" != "$previous_release" ]]; then
    printf '%s\n' \
      'Ingress, Namespace and all serving controllers do not identify one succeeded release.' >&2
    exit 2
  fi
  previous_release_safe="true"
else
  namespace_json="$work_dir/namespace-state.json"
  "${kubectl_base[@]}" get "namespace/$namespace" \
    --ignore-not-found -o json >"$namespace_json"
  if [[ -s "$namespace_json" ]]; then
    namespace_state="$(
      python -c '
import json, sys
annotations = json.load(open(sys.argv[1], encoding="utf-8")).get("metadata", {}).get("annotations", {})
print(annotations.get("archideal.io/promotion-state", "") + "|" + annotations.get("archideal.io/previous-release", ""))
' "$namespace_json"
    )"
    IFS='|' read -r recorded_state recorded_previous <<<"$namespace_state"
    if [[ "$recorded_state" == "failed" && \
          "$recorded_previous" != "none" && \
          "$recorded_previous" =~ ^[a-z0-9]([-a-z0-9]{0,37}[a-z0-9])?$ ]]; then
      previous_release="$recorded_previous"
      previous_release_safe="true"
    elif [[ -n "$recorded_state" && "$recorded_state" != "failed" ]]; then
      printf '%s\n' \
        'Promotion state is not failed but the public Ingress is absent; reconcile this drift first.' >&2
      exit 2
    fi
  fi
fi

rendered="$work_dir/rendered"
bundle="$work_dir/archideal-production.yaml"
runtime_apps_bundle="$work_dir/archideal-runtime-apps.yaml"
invocation_metadata="$work_dir/invocation.json"
python "$script_dir/render.py" --values "$values_file" --output "$rendered"
python "$script_dir/prepare-invocation-jobs.py" \
  --bootstrap "$rendered/base/bootstrap.yaml" \
  --kafka "$rendered/base/preflight.yaml" \
  --private-network "$rendered/base/private-network-preflight.yaml" \
  --synthetic "$rendered/overlays/production/synthetic-smoke.yaml" \
  --metadata-output "$invocation_metadata"
read_invocation_value() {
  python -c \
    'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))[sys.argv[2]])' \
    "$invocation_metadata" "$1"
}
invocation_id="$(read_invocation_value invocation_id)"
apisix_bootstrap_job="$(read_invocation_value apisix_bootstrap_job)"
kafka_preflight_job="$(read_invocation_value kafka_preflight_job)"
private_network_preflight_job="$(read_invocation_value private_network_preflight_job)"
production_smoke_job="$(read_invocation_value production_smoke_job)"
smoke_device_id="$(read_invocation_value smoke_device_id)"
kubectl kustomize "$rendered/overlays/production" >"$bundle"
kubectl kustomize "$rendered/runtime-apps" >"$runtime_apps_bundle"
kubectl --context "$context" apply --dry-run=client -f "$bundle" >/dev/null
kubectl --context "$context" apply --dry-run=client -f "$runtime_apps_bundle" >/dev/null
apply_cluster_file() {
  "${kubectl_base[@]}" apply --server-side --field-manager=archideal-production -f "$1"
}
apply_file() {
  "${kubectl_ns[@]}" apply --server-side --field-manager=archideal-production -f "$1"
}
wait_created_once_external_secret() {
  local name="$1"
  if ! "${kubectl_ns[@]}" wait \
    --for=condition=Ready \
    "externalsecret/$name" \
    --timeout="$timeout"; then
    "${kubectl_ns[@]}" get "externalsecret/$name" -o yaml >&2 || true
    return 1
  fi
  local target refresh_policy secret_release owner immutable
  target="$(
    "${kubectl_ns[@]}" get "externalsecret/$name" \
      -o jsonpath='{.spec.target.name}'
  )"
  refresh_policy="$(
    "${kubectl_ns[@]}" get "externalsecret/$name" \
      -o jsonpath='{.spec.refreshPolicy}'
  )"
  secret_release="$(
    "${kubectl_ns[@]}" get "secret/$name" \
      -o jsonpath='{.metadata.labels.archideal\.io/release}'
  )"
  owner="$(
    "${kubectl_ns[@]}" get "secret/$name" \
      -o 'jsonpath={.metadata.ownerReferences[?(@.kind=="ExternalSecret")].name}'
  )"
  if [[ "$target" != "$name" || "$refresh_policy" != "CreatedOnce" || \
        "$secret_release" != "$release_id" || "$owner" != "$name" ]]; then
    printf '%s\n' \
      "ExternalSecret/$name did not produce its owned CreatedOnce release Secret." >&2
    return 1
  fi
  "${kubectl_ns[@]}" patch "secret/$name" \
    --type=merge --patch '{"immutable":true}' >/dev/null
  immutable="$(
    "${kubectl_ns[@]}" get "secret/$name" -o jsonpath='{.immutable}'
  )"
  if [[ "$immutable" != "true" ]]; then
    printf 'Release Secret did not become immutable: %s\n' "$name" >&2
    return 1
  fi
}
force_and_wait_periodic_external_secret() {
  local name="$1"
  local target_namespace="${2:-$namespace}"
  local kubectl_target=(kubectl --context "$context" --namespace "$target_namespace")
  local previous_refresh sync_token state refresh ready deadline
  previous_refresh="$(
    "${kubectl_target[@]}" get "externalsecret/$name" \
      -o jsonpath='{.status.refreshTime}' 2>/dev/null || true
  )"
  sleep 1
  sync_token="$(python -c 'import time; print(time.time_ns())')"
  "${kubectl_target[@]}" annotate "externalsecret/$name" \
    "force-sync=$sync_token" --overwrite >/dev/null
  deadline="$((SECONDS + timeout_seconds))"
  while ((SECONDS < deadline)); do
    state="$(
      "${kubectl_target[@]}" get "externalsecret/$name" -o json | python -c '
import json, sys
resource = json.load(sys.stdin)
status = resource.get("status", {})
refresh = status.get("refreshTime", "")
ready = next(
    (item.get("status", "") for item in status.get("conditions", []) if item.get("type") == "Ready"),
    "",
)
print(f"{refresh}|{ready}")
'
    )"
    IFS='|' read -r refresh ready <<<"$state"
    if [[ -n "$refresh" && "$refresh" != "$previous_refresh" && "$ready" == "True" ]]; then
      return 0
    fi
    sleep 2
  done
  printf 'ExternalSecret did not complete a fresh reconciliation: %s\n' "$name" >&2
  "${kubectl_target[@]}" get "externalsecret/$name" -o yaml >&2 || true
  return 1
}

printf 'Phase 1/6: namespace and server-side admission validation\n'
mutation_started="true"
apply_cluster_file "$rendered/base/namespace.yaml"
apply_cluster_file "$rendered/runtime-apps/namespace.yaml"
"${kubectl_base[@]}" get "namespace/$runtime_apps_namespace" >/dev/null
annotate_promotion_state in-progress
"${kubectl_base[@]}" apply --server-side \
  --field-manager=archideal-production --dry-run=server -f "$bundle" >/dev/null
"${kubectl_base[@]}" apply --server-side \
  --field-manager=archideal-production --dry-run=server \
  -f "$runtime_apps_bundle" >/dev/null

printf 'Phase 2/6: configuration, secrets, private DNS and policies\n'
apply_file "$rendered/base/serviceaccounts.yaml"
apply_cluster_file "$runtime_apps_bundle"
apply_file "$rendered/base/configuration.yaml"
apply_file "$rendered/base/services.yaml"
apply_file "$rendered/overlays/production/platform-contract.yaml"
apply_file "$rendered/overlays/production/external-secrets.yaml"
wait_created_once_external_secret "$runtime_secret_name"
wait_created_once_external_secret "$runtime_controller_tls_secret_name"
force_and_wait_periodic_external_secret archideal-registry-credentials "$namespace"
force_and_wait_periodic_external_secret \
  archideal-registry-credentials "$runtime_apps_namespace"
"${kubectl_ns[@]}" get "secret/$runtime_secret_name" >/dev/null
"${kubectl_ns[@]}" get "secret/$runtime_controller_tls_secret_name" >/dev/null
"${kubectl_ns[@]}" get secret/archideal-registry-credentials >/dev/null
"${kubectl_base[@]}" --namespace "$runtime_apps_namespace" \
  get secret/archideal-registry-credentials >/dev/null
"${kubectl_ns[@]}" get "secret/$runtime_secret_name" -o json | python -c '
import base64, json, sys
secret = json.load(sys.stdin)
encoded = secret.get("data", {}).get("dealhost-runtime-controller-token", "")
try:
    token = base64.b64decode(encoded, validate=True)
except Exception as exc:
    raise SystemExit("Runtime-controller token is not valid base64") from exc
if len(token) < 32 or any(byte <= 0x20 or byte >= 0x7f for byte in token):
    raise SystemExit("Runtime-controller token must be at least 32 visible ASCII bytes")
'
"${kubectl_ns[@]}" get "secret/$runtime_controller_tls_secret_name" -o json | python -c '
import base64, json, sys
data = json.load(sys.stdin).get("data", {})
required = {"tls.crt", "tls.key", "ca.crt"}
if set(data) != required:
    raise SystemExit("Runtime-controller TLS Secret must contain exactly tls.crt, tls.key and ca.crt")
decoded = {key: base64.b64decode(data[key], validate=True) for key in required}
if not decoded["tls.crt"].startswith(b"-----BEGIN CERTIFICATE-----"):
    raise SystemExit("Runtime-controller certificate is not PEM")
if not decoded["ca.crt"].startswith(b"-----BEGIN CERTIFICATE-----"):
    raise SystemExit("Runtime-controller CA is not PEM")
if not decoded["tls.key"].startswith(b"-----BEGIN PRIVATE KEY-----"):
    raise SystemExit("Runtime-controller key must be unencrypted PKCS#8 PEM")
'
"${kubectl_ns[@]}" get "secret/$runtime_secret_name" \
  -o go-template='{{ index .data "valkey-url" }}' | \
  python "$script_dir/validate-valkey-url.py" --expected-host "$valkey_host"
apply_file "$rendered/base/private-network-preflight.yaml"
if ! "${kubectl_ns[@]}" wait --for=condition=complete \
  "job/$private_network_preflight_job" --timeout="$timeout"; then
  "${kubectl_ns[@]}" logs \
    "job/$private_network_preflight_job" --all-containers=true >&2 || true
  "${kubectl_ns[@]}" get job,pod \
    --selector="app.kubernetes.io/name=private-network-preflight,archideal.io/invocation=$invocation_id" \
    -o wide >&2 || true
  exit 1
fi
apply_file "$rendered/base/network-policies.yaml"

runtime_secret_version="$(
  "${kubectl_ns[@]}" get "secret/$runtime_secret_name" \
    -o jsonpath='{.metadata.resourceVersion}'
)"
runtime_controller_tls_secret_version="$(
  "${kubectl_ns[@]}" get "secret/$runtime_controller_tls_secret_name" \
    -o jsonpath='{.metadata.resourceVersion}'
)"
runtime_config_versions="$(
  "${kubectl_ns[@]}" get \
    configmap/archideal-runtime \
    configmap/apisix-production-config \
    configmap/apisix-bootstrap \
    -o jsonpath='{range .items[*]}{.metadata.name}:{.metadata.resourceVersion}{"\\n"}{end}'
)"
runtime_revision="$(
  python -c \
    'import hashlib, sys; print(hashlib.sha256("\n".join(sys.argv[1:]).encode()).hexdigest())' \
    "$release_id" "$runtime_secret_version" \
    "$runtime_controller_tls_secret_version" "$runtime_config_versions"
)"
controller_dir="$work_dir/controllers"
python "$script_dir/prepare-rollouts.py" \
  --revision "$runtime_revision" \
  --output "$controller_dir" \
  "$rendered/base/workloads.yaml" \
  "$rendered/base/runtime-management.yaml" \
  "$rendered/base/consumers.yaml" >/dev/null
"${kubectl_ns[@]}" apply --server-side \
  --field-manager=archideal-production --dry-run=server -f "$controller_dir" >/dev/null

printf 'Phase 3/6: Kafka contract, schema checks and migrations\n'
apply_file "$rendered/base/preflight.yaml"
if ! "${kubectl_ns[@]}" wait \
  --for=condition=complete \
  "job/$kafka_preflight_job" \
  --timeout="$timeout"; then
  "${kubectl_ns[@]}" get job,pod \
    --selector="app.kubernetes.io/name=kafka-preflight,archideal.io/invocation=$invocation_id" \
    -o wide >&2 || true
  exit 1
fi
apply_file "$rendered/base/jobs.yaml"
if ! "${kubectl_ns[@]}" wait \
  --for=condition=complete \
  --selector="app.kubernetes.io/component=migration,archideal.io/release=$release_id" \
  jobs.batch \
  --timeout="$timeout"; then
  "${kubectl_ns[@]}" get jobs,pods \
    --selector="app.kubernetes.io/component=migration,archideal.io/release=$release_id" \
    -o wide >&2 || true
  exit 1
fi

printf 'Phase 4/6: application rollouts, availability and observability controls\n'
apply_file "$rendered/base/availability.yaml"
apply_file "$rendered/base/autoscaling.yaml"
apply_file "$rendered/base/observability.yaml"
for controller_name in "${controller_order[@]}"; do
  controller_manifest="$controller_dir/$controller_name.yaml"
  if [[ ! -f "$controller_manifest" ]]; then
    printf 'Prepared controller manifest is missing: %s\n' "$controller_name" >&2
    exit 1
  fi
  apply_file "$controller_manifest"
  controller_kind="deployment"
  if [[ "$controller_name" == "mqtt-kafka-bridge" ]]; then
    controller_kind="statefulset"
  fi
  scale_deadline="$((SECONDS + timeout_seconds))"
  while ((SECONDS < scale_deadline)); do
    minimum_replicas="$(
      "${kubectl_ns[@]}" get "hpa/$controller_name" \
        -o jsonpath='{.spec.minReplicas}'
    )"
    desired_replicas="$(
      "${kubectl_ns[@]}" get "$controller_kind/$controller_name" \
        -o jsonpath='{.spec.replicas}'
    )"
    if [[ "$minimum_replicas" =~ ^[1-9][0-9]*$ && \
          "$desired_replicas" =~ ^[1-9][0-9]*$ && \
          "$desired_replicas" -ge "$minimum_replicas" ]]; then
      break
    fi
    sleep 2
  done
  if ((SECONDS >= scale_deadline)); then
    printf 'HPA did not establish minimum scale for %s.\n' "$controller_name" >&2
    exit 1
  fi
  "${kubectl_ns[@]}" rollout status \
    "$controller_kind/$controller_name" --timeout="$timeout"
done

printf 'Phase 5/6: APISIX route bootstrap\n'
apply_file "$rendered/base/bootstrap.yaml"
if ! "${kubectl_ns[@]}" wait \
  --for=condition=complete \
  "job/$apisix_bootstrap_job" \
  --timeout="$timeout"; then
  "${kubectl_ns[@]}" get job,pod \
    --selector="app.kubernetes.io/name=apisix-bootstrap,archideal.io/invocation=$invocation_id" \
    -o wide >&2 || true
  exit 1
fi

printf 'Phase 6/6: public TLS Ingress promotion\n'
apply_file "$rendered/overlays/production/ingress.yaml"
"${kubectl_ns[@]}" annotate ingress/archideal \
  "archideal.io/promotion-state=in-progress" \
  "archideal.io/promotion-release=$release_id" \
  "archideal.io/active-release=none" \
  "archideal.io/previous-release=$previous_release" \
  "archideal.io/promotion-invocation=$invocation_id" \
  --overwrite >/dev/null
"${kubectl_ns[@]}" wait \
  --for=condition=Ready \
  "certificate.cert-manager.io/$tls_secret_name" \
  --timeout="$timeout"
"${kubectl_ns[@]}" wait \
  --for=jsonpath='{.status.loadBalancer.ingress[0]}' \
  ingress/archideal \
  --timeout="$timeout"
"${kubectl_ns[@]}" get "secret/$tls_secret_name" \
  -o jsonpath='{.data.tls\.crt}{"\n"}' | grep -q .

apply_file "$rendered/overlays/production/synthetic-smoke.yaml"
if ! "${kubectl_ns[@]}" wait \
  --for=condition=complete \
  "job/$production_smoke_job" \
  --timeout="$timeout"; then
  "${kubectl_ns[@]}" logs \
    "job/$production_smoke_job" --all-containers=true >&2 || true
  exit 1
fi

ingest_token_file="$work_dir/dealdata-ingest-token"
(umask 077; : > "$ingest_token_file")
"${kubectl_ns[@]}" get "secret/$runtime_secret_name" \
  -o go-template='{{ index .data "dealdata-ingest-token" }}' | \
  python -c '
import base64, sys
encoded = sys.stdin.buffer.read().strip()
sys.stdout.buffer.write(base64.b64decode(encoded, validate=True))
' > "$ingest_token_file"
if [[ ! -s "$ingest_token_file" ]]; then
  printf 'The Ready runtime Secret contains an empty DEALData ingest token.\n' >&2
  exit 1
fi
ARCHIDEAL_BASE_URL="https://$public_host" \
ARCHIDEAL_BEARER_TOKEN_FILE="$smoke_token_file" \
ARCHIDEAL_INGEST_TOKEN_FILE="$ingest_token_file" \
  python "$script_dir/../../scripts/check-architecture.py" \
    --production \
    --exercise-api-ingest \
    --device-id "$smoke_device_id"
python "$script_dir/../../scripts/check-device-registry.py" \
  --base-url "https://$public_host/dealiot" \
  --bearer-token-file "$smoke_token_file" \
  --device-id "${smoke_device_id}-registry"

success_controllers_json="$work_dir/success-controllers.json"
success_pods_json="$work_dir/success-pods.json"
"${kubectl_ns[@]}" get deployments.apps,statefulsets.apps \
  -o json >"$success_controllers_json"
"${kubectl_ns[@]}" get pods \
  --selector='app.kubernetes.io/part-of=archideal' -o json >"$success_pods_json"
python "$script_dir/validate-release-coherence.py" \
  --controllers "$success_controllers_json" \
  --pods "$success_pods_json" \
  --values "$values_file" \
  --expected-release "$release_id" >/dev/null
promoted_ingress_release="$(
  "${kubectl_ns[@]}" get ingress/archideal \
    -o jsonpath='{.metadata.labels.archideal\.io/release}'
)"
if [[ "$promoted_ingress_release" != "$release_id" ]]; then
  printf '%s\n' \
    'The promoted Ingress release does not match all serving controllers.' >&2
  exit 1
fi
"${kubectl_ns[@]}" annotate ingress/archideal \
  "archideal.io/promotion-state=succeeded" \
  "archideal.io/promotion-release=$release_id" \
  "archideal.io/active-release=$release_id" \
  "archideal.io/previous-release=$previous_release" \
  "archideal.io/promotion-invocation=$invocation_id" \
  --overwrite >/dev/null
annotate_promotion_state succeeded
"${kubectl_ns[@]}" get ingress/archideal -o wide
printf 'Release %s promoted successfully on context %s.\n' "$release_id" "$context"
promotion_succeeded="true"
