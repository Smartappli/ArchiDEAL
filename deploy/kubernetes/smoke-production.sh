#!/usr/bin/env bash
set -Eeuo pipefail

namespace="archideal"
timeout="5m"
values_file=""
context=""
smoke_token_file=""
ingest_token_file=""
work_dir=""

usage() {
  printf '%s\n' \
    "Usage: $0 --values PATH --context KUBECTL_CONTEXT \\" \
    "          --smoke-token-file PATH --ingest-token-file PATH [OPTIONS]" \
    "" \
    "Runs a fresh MQTT-to-database production synthetic and the authenticated API gate." \
    "" \
    "Options:" \
    "  --timeout DURATION    Job/readiness timeout (default: 5m)"
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
    --smoke-token-file)
      smoke_token_file="${2:-}"
      shift 2
      ;;
    --ingest-token-file)
      ingest_token_file="${2:-}"
      shift 2
      ;;
    --timeout)
      timeout="${2:-}"
      shift 2
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
      -z "$ingest_token_file" ]]; then
  usage >&2
  exit 2
fi
for file in "$values_file" "$smoke_token_file" "$ingest_token_file"; do
  if [[ ! -s "$file" ]]; then
    printf 'Required input file does not exist or is empty: %s\n' "$file" >&2
    exit 2
  fi
done
if [[ ! "$timeout" =~ ^[1-9][0-9]*(s|m|h)$ ]]; then
  printf 'Timeout must be a positive kubectl duration (for example 5m).\n' >&2
  exit 2
fi
for executable in python kubectl; do
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
ingest_token_file="$(resolve_path "$ingest_token_file")"
release_id="$(read_value RELEASE_ID)"
runtime_secret_name="archideal-runtime-secrets-$release_id"
public_host="$(read_value PUBLIC_HOST)"
expected_console_image="$(read_value IMAGE_DEALIOT_CONSOLE)"

known_context="$(kubectl config get-contexts "$context" -o name 2>/dev/null || true)"
if [[ "$known_context" != "$context" ]]; then
  printf 'kubectl context not found or ambiguous: %s\n' "$context" >&2
  exit 2
fi

work_dir="$(mktemp -d -t archideal-production-smoke.XXXXXXXX)"
cleanup() {
  if [[ -n "$work_dir" && "$work_dir" == /tmp/archideal-production-smoke.* && \
        -d "$work_dir" ]]; then
    rm -rf -- "$work_dir"
  fi
}
trap cleanup EXIT

rendered="$work_dir/rendered"
invocation_metadata="$work_dir/invocation.json"
python "$script_dir/render.py" --values "$values_file" --output "$rendered"
python "$script_dir/prepare-invocation-jobs.py" \
  --synthetic "$rendered/overlays/production/synthetic-smoke.yaml" \
  --metadata-output "$invocation_metadata"
read_invocation_value() {
  python -c \
    'import json, sys; print(json.load(open(sys.argv[1], encoding="utf-8"))[sys.argv[2]])' \
    "$invocation_metadata" "$1"
}
invocation_id="$(read_invocation_value invocation_id)"
production_smoke_job="$(read_invocation_value production_smoke_job)"
smoke_device_id="$(read_invocation_value smoke_device_id)"
synthetic_manifest="$rendered/overlays/production/synthetic-smoke.yaml"

kubectl_ns=(kubectl --context "$context" --namespace "$namespace")
if ! kubectl --context "$context" get "namespace/$namespace" >/dev/null; then
  printf 'The ArchiDEAL production namespace is missing.\n' >&2
  exit 2
fi
if ! "${kubectl_ns[@]}" get \
  serviceaccount/archideal-runtime \
  "secret/$runtime_secret_name" \
  networkpolicy.networking.k8s.io/production-smoke-egress >/dev/null; then
  printf 'The deployed production smoke prerequisites are incomplete.\n' >&2
  exit 2
fi
controllers_json="$work_dir/controllers.json"
pods_json="$work_dir/pods.json"
ingress_json="$work_dir/ingress.json"
"${kubectl_ns[@]}" get deployments.apps,statefulsets.apps \
  --selector='app.kubernetes.io/part-of=archideal' -o json >"$controllers_json"
"${kubectl_ns[@]}" get pods \
  --selector='app.kubernetes.io/part-of=archideal' -o json >"$pods_json"
"${kubectl_ns[@]}" get ingress/archideal -o json >"$ingress_json"
if ! python "$script_dir/validate-release-coherence.py" \
  --controllers "$controllers_json" \
  --pods "$pods_json" \
  --expected-release "$release_id" \
  --values "$values_file" \
  --ingress "$ingress_json" \
  --expected-host "$public_host" >/dev/null; then
  printf '%s\n' \
    'The live controllers, Pods, images and succeeded Ingress do not match the values file.' >&2
  exit 2
fi

existing_smoke_job="$(
  "${kubectl_ns[@]}" get "job/$production_smoke_job" \
    --ignore-not-found -o name
)"
if [[ -n "$existing_smoke_job" ]]; then
  printf 'Refusing to reuse an existing production smoke Job: %s\n' \
    "$production_smoke_job" >&2
  exit 2
fi

"${kubectl_ns[@]}" apply --dry-run=client -f "$synthetic_manifest" >/dev/null
"${kubectl_ns[@]}" apply --server-side \
  --field-manager=archideal-production-smoke --dry-run=server \
  -f "$synthetic_manifest" >/dev/null
"${kubectl_ns[@]}" apply --server-side \
  --field-manager=archideal-production-smoke -f "$synthetic_manifest"
if ! "${kubectl_ns[@]}" wait \
  --for=condition=complete "job/$production_smoke_job" --timeout="$timeout"; then
  "${kubectl_ns[@]}" logs \
    "job/$production_smoke_job" --all-containers=true >&2 || true
  "${kubectl_ns[@]}" get job,pod \
    --selector="app.kubernetes.io/name=production-smoke,archideal.io/invocation=$invocation_id" \
    -o wide >&2 || true
  exit 1
fi
smoke_job_json="$work_dir/production-smoke-job.json"
"${kubectl_ns[@]}" get "job/$production_smoke_job" -o json >"$smoke_job_json"
python "$script_dir/validate-production-smoke-job.py" \
  --job "$smoke_job_json" \
  --expected-release "$release_id" \
  --expected-invocation "$invocation_id" \
  --expected-image "$expected_console_image" >/dev/null

ARCHIDEAL_BASE_URL="https://$public_host" \
ARCHIDEAL_BEARER_TOKEN_FILE="$smoke_token_file" \
ARCHIDEAL_INGEST_TOKEN_FILE="$ingest_token_file" \
  python "$script_dir/../../scripts/check-architecture.py" \
    --production \
    --exercise-api-ingest \
    --device-id "$smoke_device_id"
printf 'Fresh production smoke %s passed for release %s.\n' \
  "$invocation_id" "$release_id"
