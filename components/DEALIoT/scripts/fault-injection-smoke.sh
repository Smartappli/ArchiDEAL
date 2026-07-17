#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILES=(-f docker-compose.yml -f docker-compose.dev.yml)
FAULT_CONSUMER_TIMEOUT_MS="${FAULT_CONSUMER_TIMEOUT_MS:-60000}"

compose() {
  docker compose "${COMPOSE_FILES[@]}" "$@"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 127
  fi
}

publish_fixture() {
  local event_id="$1"
  local network_name="$2"
  local payload

  payload="$(printf '{"device_id":"%s","timestamp":"%s","payload":{"temperature_c":21.5}}' \
    "$event_id" "$(date -u +%Y-%m-%dT%H:%M:%SZ)")"
  docker run --rm --network "$network_name" eclipse-mosquitto:2.0.18 \
    mosquitto_pub -h vernemq1 -p 1883 -u admin -P "$VERNEMQ_ADMIN_PASSWORD" \
    -q 1 -t "devices/${event_id}/sensor" -m "$payload"
}

consume_count() {
  local event_id="$1"
  local output

  output="$(compose exec -T kafka2 /opt/kafka/bin/kafka-console-consumer.sh \
    --bootstrap-server kafka2:9092 --topic raw.sensor --from-beginning \
    --timeout-ms "$FAULT_CONSUMER_TIMEOUT_MS" --max-messages 500 2>/dev/null || true)"
  grep -F -c -- "$event_id" <<<"$output" || true
}

assert_bounded_delivery() {
  local event_id="$1"
  local count

  count="$(consume_count "$event_id")"
  if [ "$count" -lt 1 ] || [ "$count" -gt 2 ]; then
    echo "Expected one delivery (at most one duplicate) for ${event_id}; observed ${count}" >&2
    exit 1
  fi
}

require_command docker
: "${VERNEMQ_ADMIN_PASSWORD:?VERNEMQ_ADMIN_PASSWORD must be set}"

bridge_container="$(compose ps -q mqtt-kafka-bridge)"
network_name="$(docker inspect --format '{{range $name, $_ := .NetworkSettings.Networks}}{{if contains "ingest_net" $name}}{{$name}}{{end}}{{end}}' "$bridge_container")"
if [ -z "$network_name" ]; then
  echo "Unable to resolve the Compose ingestion network" >&2
  exit 1
fi

run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
queued_event="fault-queued-${run_id}"
broker_event="fault-broker-${run_id}"

echo "Injecting a crash between MQTT receipt and Kafka acknowledgement"
compose stop kafka1 kafka2 kafka3
publish_fixture "$queued_event" "$network_name"
sleep 2
docker kill "$bridge_container" >/dev/null
compose start kafka1 kafka2 kafka3
sleep 10
assert_bounded_delivery "$queued_event"

echo "Injecting a single Kafka broker outage"
compose stop kafka1
publish_fixture "$broker_event" "$network_name"
sleep 5
compose start kafka1
sleep 10
assert_bounded_delivery "$broker_event"

echo "Fault-injection smoke passed with no loss and bounded duplicates"
