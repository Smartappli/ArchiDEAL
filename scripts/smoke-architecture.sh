#!/usr/bin/env bash
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Run ./scripts/bootstrap-env.sh first." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

python scripts/check-architecture.py --health-only

bridge_ready=false
for _attempt in {1..60}; do
  if docker compose exec -T mqtt-kafka-bridge \
    /usr/local/bin/dealiot-mqtt-kafka-bridge --healthcheck; then
    bridge_ready=true
    break
  fi
  sleep 2
done
if [[ "$bridge_ready" != true ]]; then
  echo "MQTT-to-Kafka bridge did not become ready." >&2
  exit 1
fi

device_id="archideal-smoke-$(date +%s)"
timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
gps_message_id="$device_id-gps"
sensor_message_id="$device_id-sensor"
gps_payload=$(printf \
  '{"message_id":"%s","timestamp":"%s","latitude":50.8503,"longitude":4.3517}' \
  "$gps_message_id" "$timestamp")
sensor_payload=$(printf \
  '{"message_id":"%s","timestamp":"%s","sensor_type":"temperature","value":21.5,"unit":"celsius"}' \
  "$sensor_message_id" "$timestamp")

python scripts/check-device-registry.py --device-id "$device_id-registry"

publish() {
  local topic=$1
  local payload=$2
  docker compose --profile tools run --rm --no-deps mqtt-client \
    -h vernemq -p 1883 -u admin -P "$VERNEMQ_ADMIN_PASSWORD" \
    -q 1 -t "$topic" -m "$payload"
}

publish "devices/$device_id/gps" "$gps_payload"
publish "devices/$device_id/sensor" "$sensor_payload"
python scripts/check-architecture.py --device-id "$device_id"

# A source-provided stable message_id is scoped by the bridge to this device and
# topic. Replaying the same source event must therefore remain idempotent in DEALData.
publish "devices/$device_id/gps" "$gps_payload"
python scripts/check-architecture.py --device-id "$device_id"

echo "ArchiDEAL end-to-end smoke test passed for $device_id."
