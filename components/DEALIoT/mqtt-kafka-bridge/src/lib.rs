use base64::Engine;
use chrono::{TimeZone, Utc};
use dealiot_event_contracts::{
    build_dlq_event, now_iso, validate_event, DLQ_TOPIC, RAW_GPS_TOPIC, RAW_IMAGE2D_META_TOPIC,
    RAW_IMAGE3D_META_TOPIC, RAW_SENSOR_TOPIC, RAW_VIDEO2D_META_TOPIC, RAW_VIDEO3D_META_TOPIC,
};
use ring::digest::{digest, SHA256};
use serde_json::{json, Map, Value};
use std::collections::BTreeSet;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use thiserror::Error;
use uuid::Uuid;

const DEFAULT_MQTT_TOPICS: &str = "$share/ingestors/devices/#,$share/ingestors/wildfi/#";
const MQTT_TLS_DEFAULT_PORT: u16 = 8883;
const UNIX_MILLISECONDS_THRESHOLD: f64 = 10_000_000_000.0;
const WILDFI_TOPIC_MARKERS: &[&str] = &["wildfi", "wild-fi"];
const WILDFI_TAG_MARKERS: &[&str] = &["tags", "tag", "devices"];
const WILDFI_SENSOR_MARKERS: &[&str] = &[
    "acc",
    "accelerometer",
    "bme",
    "decoded",
    "environment",
    "gateway",
    "imu",
    "mag",
    "metadata",
    "move",
    "movement",
    "prox",
    "proximity",
    "sensor",
    "telemetry",
];
const TRUTHY_VALUES: &[&str] = &["1", "true", "yes", "on"];

#[derive(Debug, Error)]
pub enum BridgeError {
    #[error("{0}")]
    Config(String),
    #[error(transparent)]
    Io(#[from] std::io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
}

#[derive(Debug, Clone)]
pub struct BridgeConfig {
    pub mqtt_client_id: String,
    pub mqtt_clean_session: bool,
    pub mqtt_host: String,
    pub mqtt_port: u16,
    pub mqtt_username: Option<String>,
    pub mqtt_password: Option<String>,
    pub mqtt_tls_enabled: bool,
    pub mqtt_tls_ca_file: Option<String>,
    pub mqtt_tls_cert_file: Option<String>,
    pub mqtt_tls_key_file: Option<String>,
    pub mqtt_tls_insecure_skip_verify: bool,
    pub mqtt_topics: Vec<String>,
    pub wildfi_topic_prefixes: Vec<String>,
    pub kafka_bootstrap_servers: String,
    pub default_kafka_topic: String,
    pub bridge_health_port: u16,
    pub bridge_health_bind: String,
}

impl BridgeConfig {
    pub fn from_env() -> Result<Self, BridgeError> {
        let mqtt_port = env_u16("MQTT_PORT", 1883)?;
        let legacy_topic = env::var("MQTT_TOPIC")
            .ok()
            .filter(|value| !value.trim().is_empty());
        let mqtt_topics_default = legacy_topic.as_deref().unwrap_or(DEFAULT_MQTT_TOPICS);

        Ok(Self {
            mqtt_client_id: mqtt_client_id(),
            mqtt_clean_session: bool_env("MQTT_CLEAN_SESSION", false),
            mqtt_host: env_or_default("MQTT_HOST", "vernemq1"),
            mqtt_port,
            mqtt_username: env::var("MQTT_USERNAME")
                .ok()
                .filter(|value| !value.is_empty()),
            mqtt_password: env_or_secret_file("MQTT_PASSWORD")?,
            mqtt_tls_enabled: bool_env("MQTT_TLS_ENABLED", mqtt_port == MQTT_TLS_DEFAULT_PORT),
            mqtt_tls_ca_file: env::var("MQTT_TLS_CA_FILE")
                .ok()
                .filter(|value| !value.is_empty()),
            mqtt_tls_cert_file: env::var("MQTT_TLS_CERT_FILE")
                .ok()
                .filter(|value| !value.is_empty()),
            mqtt_tls_key_file: env::var("MQTT_TLS_KEY_FILE")
                .ok()
                .filter(|value| !value.is_empty()),
            mqtt_tls_insecure_skip_verify: bool_env("MQTT_TLS_INSECURE_SKIP_VERIFY", false),
            mqtt_topics: csv_env_or_default("MQTT_TOPICS", mqtt_topics_default),
            wildfi_topic_prefixes: csv_env_or_default("WILDFI_TOPIC_PREFIXES", "wildfi,wild-fi"),
            kafka_bootstrap_servers: env_or_default(
                "KAFKA_BOOTSTRAP_SERVERS",
                "kafka1:9092,kafka2:9092,kafka3:9092",
            ),
            default_kafka_topic: env_or_default("DEFAULT_KAFKA_TOPIC", RAW_SENSOR_TOPIC),
            bridge_health_port: env_u16("BRIDGE_HEALTH_PORT", 8080)?,
            bridge_health_bind: env_or_default("BRIDGE_HEALTH_BIND", "127.0.0.1"),
        })
    }
}

fn mqtt_client_id() -> String {
    env::var("MQTT_CLIENT_ID")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .or_else(|| {
            env::var("HOSTNAME")
                .ok()
                .filter(|value| !value.trim().is_empty())
        })
        .map_or_else(
            || format!("mqtt-kafka-bridge-{}", std::process::id()),
            |value| value.trim().to_string(),
        )
}

#[derive(Debug, Clone)]
pub struct MqttMessage {
    pub topic: String,
    pub payload: Vec<u8>,
    pub qos: i32,
    pub retain: bool,
}

#[derive(Debug, Clone)]
pub struct BuiltEvent {
    pub topic: String,
    pub key: Vec<u8>,
    pub event: Map<String, Value>,
}

pub fn env_or_default(name: &str, default: &str) -> String {
    env::var(name)
        .ok()
        .filter(|value| !value.trim().is_empty())
        .map_or_else(|| default.to_string(), |value| value.trim().to_string())
}

pub fn bool_env(name: &str, default: bool) -> bool {
    env::var(name).map_or(default, |value| {
        TRUTHY_VALUES.contains(&value.trim().to_ascii_lowercase().as_str())
    })
}

pub fn csv_env_or_default(name: &str, default: &str) -> Vec<String> {
    let value = env::var(name).unwrap_or_else(|_| default.to_string());
    let parsed = csv_items(&value);
    if parsed.is_empty() {
        csv_items(default)
    } else {
        parsed
    }
}

pub fn env_or_secret_file(name: &str) -> Result<Option<String>, BridgeError> {
    if let Ok(value) = env::var(name) {
        if !value.is_empty() {
            return Ok(Some(value));
        }
    }

    let Ok(secret_file) = env::var(format!("{name}_FILE")) else {
        return Ok(None);
    };
    let secret_path = fs::canonicalize(secret_file)?;
    let allowed = allowed_secret_directories()?;
    if !allowed
        .iter()
        .any(|directory| secret_path.starts_with(directory))
    {
        return Err(BridgeError::Config(format!(
            "{name}_FILE must point to an allowed secret directory"
        )));
    }

    Ok(Some(fs::read_to_string(secret_path)?.trim().to_string()))
}

pub fn allowed_secret_directories() -> Result<Vec<PathBuf>, BridgeError> {
    if let Ok(configured) = env::var("DEALIOT_SECRET_DIRECTORIES") {
        let mut directories = Vec::new();
        for item in env::split_paths(&configured).filter(|path| !path.as_os_str().is_empty()) {
            directories.push(absolute_path(&item)?);
        }
        return Ok(directories);
    }

    Ok(vec![
        absolute_path(Path::new("/run/secrets"))?,
        absolute_path(Path::new("/var/run/dealiot-secrets"))?,
        absolute_path(&env::current_dir()?.join("secrets"))?,
    ])
}

pub fn decode_payload(payload: &[u8]) -> Value {
    std::str::from_utf8(payload)
        .ok()
        .and_then(|text| serde_json::from_str(text).ok())
        .unwrap_or_else(|| {
            json!({
                "payload_b64": base64::engine::general_purpose::STANDARD.encode(payload),
            })
        })
}

pub fn is_wildfi_topic(topic: &str, prefixes: &[String]) -> bool {
    let parts: BTreeSet<_> = topic_parts_lower(topic).into_iter().collect();
    WILDFI_TOPIC_MARKERS
        .iter()
        .copied()
        .chain(prefixes.iter().map(String::as_str))
        .any(|marker| parts.contains(marker))
}

pub fn normalized_timestamp(value: Option<&Value>, fallback: &str) -> String {
    match value {
        None | Some(Value::Null) => fallback.to_string(),
        Some(Value::String(value)) if value.is_empty() => fallback.to_string(),
        Some(Value::Number(number)) => number.as_f64().map_or_else(
            || fallback.to_string(),
            |raw| {
                let seconds = if raw > UNIX_MILLISECONDS_THRESHOLD {
                    raw / 1000.0
                } else {
                    raw
                };
                let whole = seconds.trunc() as i64;
                let nanos = ((seconds.fract()) * 1_000_000_000.0) as u32;
                Utc.timestamp_opt(whole, nanos)
                    .single()
                    .map_or_else(|| fallback.to_string(), |dt| dt.to_rfc3339())
            },
        ),
        Some(Value::String(value)) => value.clone(),
        Some(value) => value_to_string(value),
    }
}

pub fn pick_event_timestamp(decoded: &Value, fallback: &str) -> String {
    let Some(object) = decoded.as_object() else {
        return fallback.to_string();
    };

    for field in ["timestamp", "utcTimestamp", "utc_timestamp", "time"] {
        if object.contains_key(field) {
            return normalized_timestamp(object.get(field), fallback);
        }
    }
    fallback.to_string()
}

pub fn pick_kafka_topic(topic: &str, default_topic: &str, wildfi_prefixes: &[String]) -> String {
    let lowered = topic.to_ascii_lowercase();
    let patterns = [
        (RAW_GPS_TOPIC, vec!["gps", "/gnss/", "rawgps"]),
        (
            RAW_VIDEO3D_META_TOPIC,
            vec!["video3d", "/stereo-video/", "/volumetric-video/"],
        ),
        (
            RAW_VIDEO2D_META_TOPIC,
            vec!["video2d", "/video/", "/camera-stream/"],
        ),
        (
            RAW_IMAGE2D_META_TOPIC,
            vec!["image2d", "/camera/", "/image/"],
        ),
        (
            RAW_IMAGE3D_META_TOPIC,
            vec!["image3d", "/lidar/", "/pointcloud/"],
        ),
    ];

    for (kafka_topic, topic_patterns) in patterns {
        if topic_patterns
            .iter()
            .any(|pattern| lowered.contains(pattern))
        {
            return kafka_topic.to_string();
        }
    }

    if lowered.contains("sensor")
        || (is_wildfi_topic(topic, wildfi_prefixes)
            && WILDFI_SENSOR_MARKERS
                .iter()
                .any(|marker| lowered.contains(marker)))
    {
        return RAW_SENSOR_TOPIC.to_string();
    }

    default_topic.to_string()
}

pub fn derive_device_id(topic: &str, wildfi_prefixes: &[String]) -> String {
    let parts: Vec<_> = topic.split('/').filter(|part| !part.is_empty()).collect();
    let lowered_parts: Vec<_> = parts.iter().map(|part| part.to_ascii_lowercase()).collect();

    for marker in WILDFI_TAG_MARKERS {
        if let Some(idx) = lowered_parts.iter().position(|part| part == marker) {
            if let Some(value) = parts.get(idx + 1) {
                return (*value).to_string();
            }
        }
    }

    for marker in WILDFI_TOPIC_MARKERS
        .iter()
        .copied()
        .chain(wildfi_prefixes.iter().map(String::as_str))
    {
        if let Some(idx) = lowered_parts.iter().position(|part| part == marker) {
            let next_idx = idx + 1;
            if let Some(value) = parts.get(next_idx) {
                if !WILDFI_SENSOR_MARKERS.contains(&lowered_parts[next_idx].as_str()) {
                    return (*value).to_string();
                }
            }
            if let Some(value) = parts.get(next_idx + 1) {
                return (*value).to_string();
            }
        }
    }

    parts
        .last()
        .map_or_else(|| "unknown".to_string(), |value| (*value).to_string())
}

pub fn pick_key(topic: &str, wildfi_prefixes: &[String]) -> Vec<u8> {
    derive_device_id(topic, wildfi_prefixes).into_bytes()
}

pub fn event_source_for_topic(topic: &str, wildfi_prefixes: &[String]) -> &'static str {
    if is_wildfi_topic(topic, wildfi_prefixes) {
        "wildfi-mqtt"
    } else {
        "mqtt-bridge"
    }
}

pub fn build_event(msg: &MqttMessage, config: &BridgeConfig) -> BuiltEvent {
    let kafka_topic = pick_kafka_topic(
        &msg.topic,
        &config.default_kafka_topic,
        &config.wildfi_topic_prefixes,
    );
    let device_id = derive_device_id(&msg.topic, &config.wildfi_topic_prefixes);
    let decoded = decode_payload(&msg.payload);
    let ingested_at = now_iso();
    let timestamp = pick_event_timestamp(&decoded, &ingested_at);
    let source = event_source_for_topic(&msg.topic, &config.wildfi_topic_prefixes);
    let event_id = event_id_for_delivery(source, &msg.topic, &device_id, &decoded);

    let mut event = Map::new();
    if kafka_topic == RAW_SENSOR_TOPIC {
        let payload = decoded
            .as_object()
            .cloned()
            .map_or_else(|| json!({ "value": decoded }), Value::Object);
        event.insert("device_id".to_string(), Value::String(device_id));
        event.insert("timestamp".to_string(), Value::String(timestamp.clone()));
        event.insert("ingested_at".to_string(), Value::String(ingested_at));
        event.insert("payload".to_string(), payload);
    } else if kafka_topic == RAW_GPS_TOPIC {
        let payload = decoded.as_object().cloned().unwrap_or_default();
        event.insert("device_id".to_string(), Value::String(device_id));
        event.insert(
            "timestamp".to_string(),
            Value::String(pick_event_timestamp(
                &Value::Object(payload.clone()),
                &timestamp,
            )),
        );
        event.insert("ingested_at".to_string(), Value::String(ingested_at));
        event.insert(
            "latitude".to_string(),
            payload_value(&payload, &["latitude", "latitude_deg", "lat"], json!(0.0)),
        );
        event.insert(
            "longitude".to_string(),
            payload_value(&payload, &["longitude", "longitude_deg", "lon"], json!(0.0)),
        );
        event.insert(
            "altitude_m".to_string(),
            payload_value(&payload, &["altitude_m", "altitude"], Value::Null),
        );
        event.insert(
            "speed_m_s".to_string(),
            payload_value(&payload, &["speed_m_s", "speed"], Value::Null),
        );
        event.insert(
            "heading_deg".to_string(),
            payload_value(&payload, &["heading_deg", "heading"], Value::Null),
        );
        event.insert("payload".to_string(), Value::Object(payload));
    } else {
        event = decoded.as_object().cloned().unwrap_or_default();
        event
            .entry("device_id".to_string())
            .or_insert_with(|| Value::String(device_id));
        event
            .entry("timestamp".to_string())
            .or_insert_with(|| Value::String(timestamp.clone()));
        event.insert("ingested_at".to_string(), Value::String(ingested_at));
    }

    event.insert("mqtt_topic".to_string(), Value::String(msg.topic.clone()));
    event.insert("event_id".to_string(), Value::String(event_id));
    event.insert(
        "schema_version".to_string(),
        Value::String("1.0.0".to_string()),
    );
    event.insert("occurred_at".to_string(), Value::String(timestamp));
    event.insert("qos".to_string(), json!(msg.qos));
    event.insert("retain".to_string(), json!(msg.retain));
    event.insert("source".to_string(), Value::String(source.to_string()));

    BuiltEvent {
        topic: kafka_topic,
        key: pick_key(&msg.topic, &config.wildfi_topic_prefixes),
        event,
    }
}

pub fn deterministic_event_id(source: &str, source_topic: &str, payload: &[u8]) -> String {
    let mut material = Vec::with_capacity(source.len() + source_topic.len() + payload.len() + 2);
    material.extend_from_slice(source.as_bytes());
    material.push(0);
    material.extend_from_slice(source_topic.as_bytes());
    material.push(0);
    material.extend_from_slice(payload);

    sha256_hex(&material)
}

/// Build an idempotency key without conflating equal measurements.
///
/// A source-provided delivery/measurement identity is stable across a redelivery. If the
/// source does not provide one, every MQTT delivery receives a fresh identifier: accepting a
/// possible duplicate is safer than silently discarding a legitimate repeated measurement.
pub fn event_id_for_delivery(
    source: &str,
    source_topic: &str,
    device_id: &str,
    decoded: &Value,
) -> String {
    if let Some((field, identity)) = source_event_identity(decoded) {
        let material = format!("{field}\0{device_id}\0{identity}");
        return deterministic_event_id(source, source_topic, material.as_bytes());
    }

    deterministic_event_id(source, source_topic, Uuid::new_v4().as_bytes())
}

fn source_event_identity(decoded: &Value) -> Option<(&'static str, String)> {
    let object = decoded.as_object()?;
    for field in [
        "event_id",
        "eventId",
        "message_id",
        "messageId",
        "measurement_id",
        "measurementId",
        "sequence",
        "sequence_id",
        "sequenceId",
        "counter",
    ] {
        let Some(value) = object.get(field) else {
            continue;
        };
        let identity = match value {
            Value::String(value) => value.trim().to_string(),
            Value::Number(value) => value.to_string(),
            _ => continue,
        };
        if !identity.is_empty() {
            return Some((field, identity));
        }
    }
    None
}

fn sha256_hex(material: &[u8]) -> String {
    digest(&SHA256, material)
        .as_ref()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

pub fn route_event(kafka_topic: &str, event: Map<String, Value>) -> (String, Value) {
    let errors = validate_event(kafka_topic, &event);
    if errors.is_empty() {
        return (kafka_topic.to_string(), Value::Object(event));
    }

    (
        DLQ_TOPIC.to_string(),
        build_dlq_event("mqtt-bridge", kafka_topic, errors, &event),
    )
}

fn payload_value(payload: &Map<String, Value>, names: &[&str], fallback: Value) -> Value {
    names
        .iter()
        .find_map(|name| payload.get(*name).cloned())
        .unwrap_or(fallback)
}

fn csv_items(value: &str) -> Vec<String> {
    value
        .split(',')
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .map(ToString::to_string)
        .collect()
}

fn env_u16(name: &str, default: u16) -> Result<u16, BridgeError> {
    env::var(name)
        .ok()
        .filter(|value| !value.trim().is_empty())
        .map_or(Ok(default), |value| {
            value
                .parse::<u16>()
                .map_err(|_| BridgeError::Config(format!("{name} must be a valid port")))
        })
}

fn absolute_path(path: &Path) -> Result<PathBuf, BridgeError> {
    if path.is_absolute() {
        Ok(path.to_path_buf())
    } else {
        Ok(env::current_dir()?.join(path))
    }
}

fn topic_parts_lower(topic: &str) -> Vec<String> {
    topic
        .split('/')
        .filter(|part| !part.is_empty())
        .map(|part| part.to_ascii_lowercase())
        .collect()
}

fn value_to_string(value: &Value) -> String {
    value
        .as_str()
        .map_or_else(|| value.to_string(), ToString::to_string)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn test_config() -> BridgeConfig {
        BridgeConfig {
            mqtt_client_id: "mqtt-kafka-bridge-test".to_string(),
            mqtt_clean_session: false,
            mqtt_host: "localhost".to_string(),
            mqtt_port: 1883,
            mqtt_username: None,
            mqtt_password: None,
            mqtt_tls_enabled: false,
            mqtt_tls_ca_file: None,
            mqtt_tls_cert_file: None,
            mqtt_tls_key_file: None,
            mqtt_tls_insecure_skip_verify: false,
            mqtt_topics: csv_items(DEFAULT_MQTT_TOPICS),
            wildfi_topic_prefixes: vec!["wildfi".to_string(), "wild-fi".to_string()],
            kafka_bootstrap_servers: "localhost:9092".to_string(),
            default_kafka_topic: RAW_SENSOR_TOPIC.to_string(),
            bridge_health_port: 8080,
            bridge_health_bind: "127.0.0.1".to_string(),
        }
    }

    #[test]
    fn decodes_invalid_payload_as_base64() {
        assert_eq!(decode_payload(&[0xff, 0x00, 0x88])["payload_b64"], "/wCI");
    }

    #[test]
    fn routes_topics_and_derives_device_ids() {
        let config = test_config();
        assert_eq!(
            pick_kafka_topic(
                "devices/a1/gnss/fix",
                &config.default_kafka_topic,
                &config.wildfi_topic_prefixes
            ),
            RAW_GPS_TOPIC
        );
        assert_eq!(
            derive_device_id("wildfi/tags/WF-001/gps", &config.wildfi_topic_prefixes),
            "WF-001"
        );
        assert_eq!(
            derive_device_id("/", &config.wildfi_topic_prefixes),
            "unknown"
        );
    }

    #[test]
    fn normalizes_seconds_and_milliseconds() {
        let fallback = "2026-01-01T00:00:00+00:00";
        assert_eq!(
            normalized_timestamp(Some(&json!(1_704_067_200)), fallback),
            "2024-01-01T00:00:00+00:00"
        );
        assert_eq!(
            normalized_timestamp(Some(&json!(1_704_067_200_000i64)), fallback),
            "2024-01-01T00:00:00+00:00"
        );
    }

    #[test]
    fn builds_and_routes_invalid_media_to_dlq() {
        let event = json!({
            "device_id": "cam-1",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "frame": 12
        })
        .as_object()
        .cloned()
        .unwrap();

        let (topic, routed) = route_event(RAW_VIDEO2D_META_TOPIC, event);
        assert_eq!(topic, DLQ_TOPIC);
        assert!(routed["errors"]
            .as_array()
            .unwrap()
            .contains(&json!("missing required field: bucket")));
    }

    #[test]
    fn builds_wildfi_sensor_event() {
        let config = test_config();
        let msg = MqttMessage {
            topic: "wildfi/tags/WF-001/environment".to_string(),
            payload: br#"{"utc_timestamp":1704067200000,"temperatureInDegCel":18.7}"#.to_vec(),
            qos: 1,
            retain: false,
        };

        let built = build_event(&msg, &config);
        assert_eq!(built.topic, RAW_SENSOR_TOPIC);
        assert_eq!(built.key, b"WF-001");
        assert_eq!(built.event["timestamp"], "2024-01-01T00:00:00+00:00");
        assert_eq!(built.event["source"], "wildfi-mqtt");
        assert_eq!(built.event["schema_version"], "1.0.0");
        assert_eq!(built.event["occurred_at"], "2024-01-01T00:00:00+00:00");
        assert_eq!(built.event["event_id"].as_str().unwrap().len(), 64);
    }

    #[test]
    fn identical_measurements_without_source_identity_get_distinct_delivery_ids() {
        let decoded = json!({"temperature": 20});
        let first = event_id_for_delivery("mqtt-bridge", "devices/a", "a", &decoded);
        let second = event_id_for_delivery("mqtt-bridge", "devices/a", "a", &decoded);

        assert_ne!(first, second);
        assert_eq!(first.len(), 64);
        assert_eq!(second.len(), 64);
    }

    #[test]
    fn source_identity_deduplicates_redelivery_with_device_scoped_keys() {
        let first = event_id_for_delivery(
            "mqtt-bridge",
            "devices/a",
            "a",
            &json!({"message_id": "delivery-42", "temperature": 20}),
        );
        let replay = event_id_for_delivery(
            "mqtt-bridge",
            "devices/a",
            "a",
            &json!({"message_id": "delivery-42", "temperature": 21}),
        );
        let changed = event_id_for_delivery(
            "mqtt-bridge",
            "devices/a",
            "a",
            &json!({"message_id": "delivery-43", "temperature": 20}),
        );
        let other_device = event_id_for_delivery(
            "mqtt-bridge",
            "devices/a",
            "b",
            &json!({"message_id": "delivery-42", "temperature": 20}),
        );

        assert_eq!(first, replay);
        assert_ne!(first, changed);
        assert_ne!(first, other_device);
    }
}
