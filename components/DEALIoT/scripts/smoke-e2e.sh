#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILES=(
  -f docker-compose.yml
  -f docker-compose.dev.yml
)

SMOKE_COMPOSE_UP_STEP_TIMEOUT_SECONDS="${SMOKE_COMPOSE_UP_STEP_TIMEOUT_SECONDS:-2100}"
SMOKE_COMPOSE_UP_WAIT_TIMEOUT_SECONDS="${SMOKE_COMPOSE_UP_WAIT_TIMEOUT_SECONDS:-1200}"
SMOKE_COMPOSE_READY_POLL_SECONDS="${SMOKE_COMPOSE_READY_POLL_SECONDS:-5}"
SMOKE_COMPOSE_READY_ATTEMPTS="${SMOKE_COMPOSE_READY_ATTEMPTS:-$(((SMOKE_COMPOSE_UP_WAIT_TIMEOUT_SECONDS + SMOKE_COMPOSE_READY_POLL_SECONDS - 1) / SMOKE_COMPOSE_READY_POLL_SECONDS))}"
SMOKE_COMPOSE_OUTPUT_TAIL="${SMOKE_COMPOSE_OUTPUT_TAIL:-120}"
SMOKE_FLINK_SUBMIT_TIMEOUT_SECONDS="${SMOKE_FLINK_SUBMIT_TIMEOUT_SECONDS:-180}"
SMOKE_FLINK_SUBMIT_OUTPUT_TAIL="${SMOKE_FLINK_SUBMIT_OUTPUT_TAIL:-80}"
SMOKE_FLINK_LIST_TIMEOUT_SECONDS="${SMOKE_FLINK_LIST_TIMEOUT_SECONDS:-45}"
SMOKE_MQTT_PUBLISH_STEP_TIMEOUT_SECONDS="${SMOKE_MQTT_PUBLISH_STEP_TIMEOUT_SECONDS:-45}"
SMOKE_MQTT_PUBLISH_TIMEOUT_SECONDS="${SMOKE_MQTT_PUBLISH_TIMEOUT_SECONDS:-15}"
SMOKE_KAFKA_CONSUMER_GRACE_SECONDS="${SMOKE_KAFKA_CONSUMER_GRACE_SECONDS:-15}"
SMOKE_APICURIO_STEP_TIMEOUT_SECONDS="${SMOKE_APICURIO_STEP_TIMEOUT_SECONDS:-45}"
SMOKE_APICURIO_CHECK_TIMEOUT_SECONDS="${SMOKE_APICURIO_CHECK_TIMEOUT_SECONDS:-20}"
SMOKE_DIAGNOSTIC_TIMEOUT_SECONDS="${SMOKE_DIAGNOSTIC_TIMEOUT_SECONDS:-60}"
SMOKE_DIAGNOSTIC_LOG_TAIL="${SMOKE_DIAGNOSTIC_LOG_TAIL:-60}"
SMOKE_KAFKA_DIAGNOSTIC_TOPICS="${SMOKE_KAFKA_DIAGNOSTIC_TOPICS:-raw.sensor dlq.events features.events state.latest}"
SMOKE_FLINK_EXPECTED_TASKMANAGERS="${SMOKE_FLINK_EXPECTED_TASKMANAGERS:-2}"
SMOKE_FLINK_TASKMANAGER_WAIT_ATTEMPTS="${SMOKE_FLINK_TASKMANAGER_WAIT_ATTEMPTS:-45}"
SMOKE_FLINK_REST_HOST="${SMOKE_FLINK_REST_HOST:-flink-jobmanager}"
SMOKE_FLINK_REST_PORT="${SMOKE_FLINK_REST_PORT:-8081}"
SMOKE_CANCEL_FLINK_JOB="${SMOKE_CANCEL_FLINK_JOB:-1}"

compose() {
  docker compose "${COMPOSE_FILES[@]}" "$@"
}

compose_with_timeout() {
  local timeout_seconds="$1"
  shift

  timeout --kill-after=10s "${timeout_seconds}s" docker compose "${COMPOSE_FILES[@]}" "$@"
}

require_command() {
  local command_name="$1"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 127
  fi
}

emit_smoke_error() {
  local message="$1"

  echo "$message" >&2
  if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
    printf '::error title=E2E smoke::%s\n' "$message" >&2
  fi
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    {
      printf '### E2E smoke failure\n\n'
      printf '%s\n' "$message"
    } >>"$GITHUB_STEP_SUMMARY" || true
  fi
}

timeout_seconds_from_ms() {
  local timeout_ms="$1"

  echo $(((timeout_ms + 999) / 1000 + SMOKE_KAFKA_CONSUMER_GRACE_SECONDS))
}

wait_for_topic_message() {
  local topic="$1"
  local pattern="$2"
  local timeout_ms="${3:-30000}"
  local consumer_output
  local consumer_status
  local consumer_timeout_seconds

  echo "Waiting for Kafka topic=$topic pattern=$pattern"
  consumer_timeout_seconds="$(timeout_seconds_from_ms "$timeout_ms")"

  set +e
  consumer_output="$(
    compose_with_timeout "$consumer_timeout_seconds" exec -T kafka1 \
      /opt/kafka/bin/kafka-console-consumer.sh \
      --bootstrap-server kafka1:9092 \
      --topic "$topic" \
      --from-beginning \
      --timeout-ms "$timeout_ms" \
      --max-messages 200 2>&1
  )"
  consumer_status=$?
  set -e

  if grep -F -m 1 -- "$pattern" <<<"$consumer_output"; then
    return 0
  fi

  echo "Kafka consumer exit status for ${topic}: ${consumer_status}" >&2
  if [ -n "$consumer_output" ]; then
    echo "Kafka consumer output for ${topic} (first 80 lines)" >&2
    printf '%s\n' "$consumer_output" | sed -n '1,80p' >&2
  else
    echo "Kafka consumer produced no output for ${topic}" >&2
  fi

  dump_kafka_topic_state "$topic"
  dump_flink_job_diagnostics

  emit_smoke_error "Did not observe expected message on ${topic}: ${pattern}"
  dump_smoke_diagnostics
  return 1
}

dump_kafka_topic_state() {
  local topic="$1"

  echo "Kafka topic state: ${topic}" >&2
  if ! compose_service_running kafka1; then
    echo "Kafka service kafka1 is not running; skipping topic state for ${topic}" >&2
    return 0
  fi

  compose_with_timeout "$SMOKE_DIAGNOSTIC_TIMEOUT_SECONDS" exec -T kafka1 \
    /opt/kafka/bin/kafka-topics.sh \
    --bootstrap-server kafka1:9092 \
    --describe \
    --topic "$topic" >&2 || true
  compose_with_timeout "$SMOKE_DIAGNOSTIC_TIMEOUT_SECONDS" exec -T kafka1 \
    /opt/kafka/bin/kafka-get-offsets.sh \
    --bootstrap-server kafka1:9092 \
    --topic "$topic" >&2 || true
}

compose_service_state() {
  local service="$1"
  local container_id

  container_id="$(compose ps -a -q "$service" 2>/dev/null || true)"
  if [ -z "$container_id" ]; then
    return 1
  fi

  docker inspect \
    --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.State.ExitCode}}' \
    "$container_id"
}

compose_service_running() {
  local service="$1"
  local state
  local status

  state="$(compose_service_state "$service" || true)"
  if [ -z "$state" ]; then
    return 1
  fi

  status="${state%%|*}"
  [ "$status" = "running" ]
}

wait_for_compose_service() {
  local service="$1"
  local condition="$2"
  local attempts="${3:-$SMOKE_COMPOSE_READY_ATTEMPTS}"
  local state
  local status
  local health
  local exit_code

  for _ in $(seq 1 "$attempts"); do
    state="$(compose_service_state "$service" || true)"

    if [ -n "$state" ]; then
      IFS='|' read -r status health exit_code <<<"$state"
      echo "Compose service ${service}: status=${status} health=${health} exit=${exit_code}; waiting for ${condition}"

      case "$condition" in
        healthy)
          if [ "$status" = "running" ] && [ "$health" = "healthy" ]; then
            return 0
          fi
          ;;
        running)
          if [ "$status" = "running" ]; then
            return 0
          fi
          ;;
        completed)
          if [ "$status" = "exited" ] && [ "$exit_code" = "0" ]; then
            return 0
          fi
          ;;
        *)
          echo "Unknown compose service condition: ${condition}" >&2
          return 2
          ;;
      esac

      if [ "$status" = "exited" ] && [ "$exit_code" != "0" ]; then
        emit_smoke_error "Compose service ${service} exited with code ${exit_code} while waiting for ${condition}."
        dump_smoke_diagnostics
        return 1
      fi
    else
      echo "Compose service ${service}: not created yet; waiting for ${condition}"
    fi

    sleep "$SMOKE_COMPOSE_READY_POLL_SECONDS"
  done

  emit_smoke_error "Compose service ${service} did not reach ${condition}."
  dump_smoke_diagnostics
  return 1
}

wait_for_core_event_flow_services() {
  wait_for_compose_service kafka1 healthy
  wait_for_compose_service kafka2 healthy
  wait_for_compose_service kafka3 healthy
  wait_for_compose_service kafka-init completed
  wait_for_compose_service vernemq1 healthy
  wait_for_compose_service seaweedfs-pg-init completed
  wait_for_compose_service seaweedfs-filer healthy
  wait_for_compose_service seaweedfs-s3 healthy
  wait_for_compose_service seaweedfs-init completed
  wait_for_compose_service apicurio-registry running
  wait_for_compose_service apicurio-init completed
  wait_for_compose_service mqtt-kafka-bridge running
  wait_for_compose_service flink-jobmanager healthy
}

dump_flink_rest_path() {
  local label="$1"
  local path="$2"

  echo "Flink REST ${label}" >&2
  if ! compose_service_running flink-jobmanager; then
    echo "Flink JobManager is not running; skipping Flink REST ${label}" >&2
    return 0
  fi

  compose_with_timeout "$SMOKE_DIAGNOSTIC_TIMEOUT_SECONDS" run --no-deps --rm --entrypoint python flink-cli - \
    "$SMOKE_FLINK_REST_HOST" "$SMOKE_FLINK_REST_PORT" "$path" <<'PY' >&2 || true
import http.client
import json
import sys

host = sys.argv[1]
port = int(sys.argv[2])
path = sys.argv[3]

connection = http.client.HTTPConnection(host, port, timeout=5)
try:
    connection.request("GET", path)
    response = connection.getresponse()
    payload = response.read()
finally:
    connection.close()

print(f"HTTP {response.status} {response.reason}")
try:
    rendered = json.dumps(json.loads(payload), indent=2, sort_keys=True)
except Exception:
    rendered = payload.decode("utf-8", errors="replace")

print(rendered[:12000])
if len(rendered) > 12000:
    print("... truncated ...")
PY
}

dump_flink_job_diagnostics() {
  dump_flink_rest_path "overview" "/overview"
  dump_flink_rest_path "jobs overview" "/jobs/overview"

  if [ -n "${flink_job_id:-}" ]; then
    dump_flink_rest_path "job ${flink_job_id}" "/jobs/${flink_job_id}"
    dump_flink_rest_path "job ${flink_job_id} exceptions" "/jobs/${flink_job_id}/exceptions"
    dump_flink_rest_path "job ${flink_job_id} checkpoints" "/jobs/${flink_job_id}/checkpoints"
  fi
}

dump_smoke_diagnostics() {
  local diagnostic_topic
  local -a diagnostic_topics

  echo "Docker compose status" >&2
  compose ps >&2 || true

  echo "Flink running jobs" >&2
  if compose_service_running flink-jobmanager; then
    compose_with_timeout "$SMOKE_DIAGNOSTIC_TIMEOUT_SECONDS" run --no-deps --rm --entrypoint sh flink-cli -lc \
      "/opt/flink/bin/flink list -r --jobmanager flink-jobmanager:8081 || true" >&2 || true
  else
    echo "Flink JobManager is not running; skipping Flink job list" >&2
  fi
  dump_flink_job_diagnostics

  echo "Kafka topic diagnostics" >&2
  read -r -a diagnostic_topics <<<"$SMOKE_KAFKA_DIAGNOSTIC_TOPICS"
  for diagnostic_topic in "${diagnostic_topics[@]}"; do
    dump_kafka_topic_state "$diagnostic_topic"
  done

  echo "Recent event-flow logs" >&2
  compose_with_timeout "$SMOKE_DIAGNOSTIC_TIMEOUT_SECONDS" logs --no-color --tail="$SMOKE_DIAGNOSTIC_LOG_TAIL" \
    flink-jobmanager flink-taskmanager-1 flink-taskmanager-2 \
    mqtt-kafka-bridge apicurio-registry apicurio-init kafka1 kafka2 kafka3 \
    seaweedfs-filer seaweedfs-s3 seaweedfs-init seaweedfs-pg-init >&2 || true
}

wait_for_flink_job_running() {
  local job_id="$1"
  local attempts="${2:-30}"
  local list_output

  for _ in $(seq 1 "$attempts"); do
    list_output="$(
      compose_with_timeout "$SMOKE_FLINK_LIST_TIMEOUT_SECONDS" run --rm --entrypoint sh flink-cli -lc \
        "/opt/flink/bin/flink list -r --jobmanager flink-jobmanager:8081" 2>&1 || true
    )"
    printf '%s\n' "$list_output"

    if printf '%s\n' "$list_output" | grep -F "$job_id" >/dev/null; then
      return 0
    fi

    sleep 2
  done

  emit_smoke_error "Flink job $job_id did not reach RUNNING state."
  dump_smoke_diagnostics
  return 1
}

wait_for_flink_taskmanagers() {
  local expected="$SMOKE_FLINK_EXPECTED_TASKMANAGERS"
  local attempts="$SMOKE_FLINK_TASKMANAGER_WAIT_ATTEMPTS"
  local taskmanager_count

  for _ in $(seq 1 "$attempts"); do
    # Flink REST is intentionally queried only from inside the Docker test network.
    taskmanager_count="$(
      compose_with_timeout "$SMOKE_FLINK_LIST_TIMEOUT_SECONDS" run --rm --entrypoint python flink-cli - \
        "$SMOKE_FLINK_REST_HOST" "$SMOKE_FLINK_REST_PORT" "/taskmanagers" 2>/dev/null <<'PY' || true
import http.client
import json
import sys

host = sys.argv[1]
port = int(sys.argv[2])
path = sys.argv[3]

connection = http.client.HTTPConnection(host, port, timeout=5)
try:
    connection.request("GET", path)
    response = connection.getresponse()
    if response.status != 200:
        raise SystemExit(f"Flink REST returned HTTP {response.status} {response.reason}")
    print(len(json.loads(response.read()).get("taskmanagers", [])))
finally:
    connection.close()
PY
    )"
    taskmanager_count="$(tr -dc '0-9' <<<"$taskmanager_count")"
    taskmanager_count="${taskmanager_count:-0}"

    echo "Flink registered taskmanagers: ${taskmanager_count}/${expected}"
    if [ "$taskmanager_count" -ge "$expected" ]; then
      return 0
    fi

    sleep 2
  done

  emit_smoke_error "Flink did not register ${expected} TaskManagers before job submission."
  dump_smoke_diagnostics
  return 1
}

publish_mqtt_fixtures() {
  local sensor_id="$1"
  local camera_id="$2"

  compose_with_timeout "$SMOKE_MQTT_PUBLISH_STEP_TIMEOUT_SECONDS" exec -T \
    mqtt-kafka-bridge python - "$sensor_id" "$camera_id" "$SMOKE_MQTT_PUBLISH_TIMEOUT_SECONDS" <<'PY'
import json
import os
import sys
import time

from paho.mqtt import client as mqtt

sensor_id = sys.argv[1]
camera_id = sys.argv[2]
publish_timeout = float(sys.argv[3])
password = os.environ["MQTT_PASSWORD"]
client = mqtt.Client(
    mqtt.CallbackAPIVersion.VERSION2,
    client_id=f"dealiot-e2e-publisher-{sensor_id}",
)
client.username_pw_set("admin", password)


def publish_or_raise(topic, payload):
    publish_result = client.publish(
        topic,
        json.dumps(payload),
        qos=1,
    )
    publish_result.wait_for_publish(timeout=publish_timeout)
    if not publish_result.is_published():
        raise TimeoutError(f"Timed out publishing MQTT fixture to {topic}")
    if publish_result.rc != mqtt.MQTT_ERR_SUCCESS:
        raise RuntimeError(
            f"Failed publishing MQTT fixture to {topic}: "
            f"{mqtt.error_string(publish_result.rc)}"
        )

sensor_payload = {
    "timestamp": "2026-01-01T00:00:00+00:00",
    "temperature_c": 21.5,
}
invalid_media_payload = {"frame": 12}

connect_result = client.connect("vernemq1", 1883, keepalive=30)
if connect_result != mqtt.MQTT_ERR_SUCCESS:
    raise RuntimeError(f"Failed connecting to MQTT broker: {mqtt.error_string(connect_result)}")

client.loop_start()
try:
    publish_or_raise(f"devices/{sensor_id}/sensor", sensor_payload)
    publish_or_raise(f"devices/{camera_id}/video2d", invalid_media_payload)
    time.sleep(2)
finally:
    client.loop_stop()
    client.disconnect()
PY
}

check_apicurio_artifact() {
  local group="$1"
  local artifact="$2"
  local artifact_url="${registry_base}/groups/${group}/artifacts/${artifact}"
  local check_output
  local check_status

  echo "Checking Apicurio artifact ${group}/${artifact}"

  set +e
  check_output="$(
    compose_with_timeout "$SMOKE_APICURIO_STEP_TIMEOUT_SECONDS" run --rm --entrypoint sh \
      apicurio-init -lc \
      "curl --connect-timeout 5 --max-time ${SMOKE_APICURIO_CHECK_TIMEOUT_SECONDS} -fsS ${artifact_url} >/dev/null" 2>&1
  )"
  check_status=$?
  set -e

  if [ "$check_status" -ne 0 ]; then
    printf '%s\n' "$check_output" >&2
    emit_smoke_error "Failed checking Apicurio artifact at ${artifact_url}"
    dump_smoke_diagnostics
    return 1
  fi
}

cleanup_smoke() {
  local exit_code=$?
  trap - EXIT

  if [ "$SMOKE_CANCEL_FLINK_JOB" = "1" ] && [ -n "${flink_job_id:-}" ]; then
    echo "Cancelling Flink smoke job ${flink_job_id}"
    compose_with_timeout "$SMOKE_FLINK_LIST_TIMEOUT_SECONDS" run --rm --entrypoint sh flink-cli -lc \
      "/opt/flink/bin/flink cancel --jobmanager flink-jobmanager:8081 ${flink_job_id} >/dev/null 2>&1 || true" || true
  fi

  exit "$exit_code"
}

require_command docker
require_command timeout

smoke_run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$-${RANDOM}"
sensor_id="e2e-sensor-${smoke_run_id}"
camera_id="e2e-camera-${smoke_run_id}"
flink_consumer_group="flink-streaming-minimal-e2e-${smoke_run_id}"
flink_job_id=""

trap cleanup_smoke EXIT

echo "Using smoke run id: ${smoke_run_id}"

echo "Rendering compose configuration"
compose config -q

echo "Starting core event-flow services"
compose_up_log="$(mktemp)"
set +e
compose_with_timeout "$SMOKE_COMPOSE_UP_STEP_TIMEOUT_SECONDS" up -d --build \
  kafka1 kafka2 kafka3 kafka-init \
  apicurio-registry apicurio-init \
  vernemq1 mqtt-kafka-bridge \
  flink-jobmanager flink-taskmanager-1 flink-taskmanager-2 >"$compose_up_log" 2>&1
compose_up_status=$?
set -e
echo "Docker compose up output (last ${SMOKE_COMPOSE_OUTPUT_TAIL} lines)"
tail -n "$SMOKE_COMPOSE_OUTPUT_TAIL" "$compose_up_log" || true
if [ "$compose_up_status" -ne 0 ]; then
  emit_smoke_error "Core event-flow services failed to become ready."
  rm -f "$compose_up_log"
  dump_smoke_diagnostics
  exit "$compose_up_status"
fi
rm -f "$compose_up_log"
wait_for_core_event_flow_services

wait_for_flink_taskmanagers

echo "Submitting Flink streaming job"
set +e
submit_output="$(
  compose_with_timeout "$SMOKE_FLINK_SUBMIT_TIMEOUT_SECONDS" run --rm \
    -e FLINK_CONSUMER_GROUP="$flink_consumer_group" \
    flink-cli sh /opt/flink/usrlib/run-streaming-minimal.sh 2>&1
)"
submit_status=$?
set -e
printf '%s\n' "$submit_output"
if [ "$submit_status" -ne 0 ]; then
  echo "Flink submit output (last ${SMOKE_FLINK_SUBMIT_OUTPUT_TAIL} lines)" >&2
  printf '%s\n' "$submit_output" | tail -n "$SMOKE_FLINK_SUBMIT_OUTPUT_TAIL" >&2 || true
  emit_smoke_error "Flink job submission failed or timed out with status ${submit_status}. Last output: $(printf '%s\n' "$submit_output" | tail -n 20 | tr '\n' ' ' | cut -c 1-900)"
  dump_smoke_diagnostics
  exit "$submit_status"
fi

flink_job_id="$(
  printf '%s\n' "$submit_output" |
    sed -n 's/.*JobID \([0-9a-fA-F]\{32\}\).*/\1/p' |
    tail -n 1
)"
if [ -z "$flink_job_id" ]; then
  emit_smoke_error "Unable to parse Flink JobID from submit output."
  dump_smoke_diagnostics
  exit 1
fi

wait_for_flink_job_running "$flink_job_id"

publish_mqtt_fixtures "$sensor_id" "$camera_id"

wait_for_topic_message "raw.sensor" "$sensor_id"
wait_for_topic_message "dlq.events" "$camera_id"
wait_for_topic_message "features.events" "$sensor_id" 60000
wait_for_topic_message "state.latest" "$sensor_id" 60000

echo "Checking Apicurio artifacts"
registry_scheme="${APICURIO_REGISTRY_SCHEME:-http}"
registry_host="${APICURIO_REGISTRY_HOST:-apicurio-registry:8080}"
registry_base="${registry_scheme}://${registry_host}/apis/registry/v3"
check_apicurio_artifact platform dlq.events
check_apicurio_artifact telemetry raw.sensor

echo "E2E smoke test passed"
