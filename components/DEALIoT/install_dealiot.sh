#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./install_dealiot.sh [dev|staging|prod] [docker compose args...]

Examples:
  ./install_dealiot.sh dev up -d --build
  ./install_dealiot.sh staging config -q
  ./install_dealiot.sh prod up -d --wait
EOF
}

environment="${1:-dev}"
if [ "$#" -gt 0 ]; then
  shift
fi

case "$environment" in
  dev)
    overlay="docker-compose.dev.yml"
    ;;
  staging)
    overlay="docker-compose.staging.yml"
    ;;
  prod)
    overlay="docker-compose.prod.yml"
    ;;
  -h|--help|help)
    usage
    exit 0
    ;;
  *)
    echo "Unknown environment: $environment" >&2
    usage >&2
    exit 2
    ;;
esac

if [ ! -f ".env" ]; then
  echo "Missing .env. Copy .env.example to .env and fill required values." >&2
  exit 1
fi

if [ ! -f "$overlay" ]; then
  echo "Missing compose overlay: $overlay" >&2
  exit 1
fi

compose_args=("$@")
if [ "${#compose_args[@]}" -eq 0 ]; then
  compose_args=(up -d --build)
fi

docker compose -f docker-compose.yml -f "$overlay" config -q
docker compose -f docker-compose.yml -f "$overlay" "${compose_args[@]}"
