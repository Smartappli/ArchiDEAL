#!/usr/bin/env bash
set -Eeuo pipefail

namespace="archideal"
timeout="15m"
values_file=""
context=""
smoke_token_file=""
release_manifest=""
release_bundle=""
release_evidence_dir=""
schema_compatible="false"

usage() {
  printf '%s\n' \
    "Usage: $0 --values PATH --context KUBECTL_CONTEXT --smoke-token-file PATH \\" \
    "          --release-manifest PATH --release-bundle PATH \\" \
    "          --release-evidence-dir PATH --approve-schema-compatible [OPTIONS]" \
    "" \
    "Rolls back only to the recorded previous signed release by running the full deployer." \
    "It never restores or reverses a database schema." \
    "" \
    "Options:" \
    "  --timeout DURATION    Readiness timeout (default: 15m)"
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
    --timeout)
      timeout="${2:-}"
      shift 2
      ;;
    --approve-schema-compatible)
      schema_compatible="true"
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
if [[ "$schema_compatible" != "true" ]]; then
  printf '%s\n' \
    '--approve-schema-compatible is required: rollback never reverses database migrations.' >&2
  exit 2
fi
if [[ ! -f "$values_file" || ! -s "$smoke_token_file" || \
      ! -f "$release_manifest" || ! -f "$release_bundle" || \
      ! -d "$release_evidence_dir" ]]; then
  printf '%s\n' \
    'Previous values, bearer token, signed manifest, bundle and evidence are all required.' >&2
  exit 2
fi
if [[ ! "$timeout" =~ ^[1-9][0-9]*(s|m|h)$ ]]; then
  printf 'Timeout must be a positive kubectl duration (for example 15m).\n' >&2
  exit 2
fi
for executable in python kubectl; do
  if ! command -v "$executable" >/dev/null 2>&1; then
    printf 'Missing required executable: %s\n' "$executable" >&2
    exit 2
  fi
done

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
target_release="$(
  python -c '
import sys, yaml
value = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
release = value.get("RELEASE_ID", "") if isinstance(value, dict) else ""
print(release)
' "$values_file"
)"
if [[ "$target_release" == "none" || "$target_release" == "pending" || \
      ! "$target_release" =~ ^[a-z0-9]([-a-z0-9]{0,37}[a-z0-9])?$ ]]; then
  printf 'Rollback values contain an invalid RELEASE_ID.\n' >&2
  exit 2
fi
known_context="$(kubectl config get-contexts "$context" -o name 2>/dev/null || true)"
if [[ "$known_context" != "$context" ]]; then
  printf 'kubectl context not found or ambiguous: %s\n' "$context" >&2
  exit 2
fi
promotion_record="$(
  kubectl --context "$context" get "namespace/$namespace" -o json | python -c '
import json, sys
annotations = json.load(sys.stdin).get("metadata", {}).get("annotations", {})
print("|".join((
    annotations.get("archideal.io/promotion-state", ""),
    annotations.get("archideal.io/promotion-release", ""),
    annotations.get("archideal.io/previous-release", ""),
)))
'
)"
IFS='|' read -r promotion_state failed_or_active_release recorded_previous \
  <<<"$promotion_record"
if [[ "$promotion_state" != "failed" && "$promotion_state" != "succeeded" ]]; then
  printf 'No completed or failed ArchiDEAL promotion record is available.\n' >&2
  exit 2
fi
if [[ "$recorded_previous" != "$target_release" ]]; then
  printf 'Rollback target %s is not the recorded previous release %s.\n' \
    "$target_release" "${recorded_previous:-missing}" >&2
  exit 2
fi
if [[ "$promotion_state" == "failed" ]] && \
   kubectl --context "$context" --namespace "$namespace" \
     get ingress/archideal >/dev/null 2>&1; then
  printf '%s\n' \
    'A failed promotion still has a public Ingress; fence it before rollback.' >&2
  exit 2
fi
printf 'Rolling back %s to recorded signed release %s without schema downgrade.\n' \
  "${failed_or_active_release:-unknown}" "$target_release"
exec "$script_dir/deploy-production.sh" \
  --values "$values_file" \
  --context "$context" \
  --timeout "$timeout" \
  --smoke-token-file "$smoke_token_file" \
  --release-manifest "$release_manifest" \
  --release-bundle "$release_bundle" \
  --release-evidence-dir "$release_evidence_dir" \
  --approve-live-upgrade
