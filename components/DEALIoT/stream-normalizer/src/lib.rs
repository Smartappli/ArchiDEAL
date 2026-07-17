use dealiot_event_contracts::{now_iso, DLQ_TOPIC, FEATURES_EVENTS_TOPIC, STATE_LATEST_TOPIC};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;

const DEFAULT_SOURCE_TOPICS: &str =
    "raw.sensor,raw.gps,raw.image2d.meta,raw.image3d.meta,raw.video2d.meta,raw.video3d.meta";

const WILDFI_TOPIC_MARKERS: &[&str] = &["wildfi", "wild-fi"];
const WILDFI_TAG_MARKERS: &[&str] = &["devices", "tag", "tags"];
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

#[derive(Debug, Clone)]
pub struct NormalizerConfig {
    pub bootstrap_servers: String,
    pub consumer_group: String,
    pub source_topics: Vec<String>,
    pub features_topic: String,
    pub state_topic: String,
    pub dlq_topic: String,
    pub state_output_enabled: bool,
    pub health_bind: String,
    pub health_port: u16,
}

impl NormalizerConfig {
    pub fn from_env() -> Self {
        Self {
            bootstrap_servers: env_or_default(
                "KAFKA_BOOTSTRAP_SERVERS",
                "kafka1:9092,kafka2:9092,kafka3:9092",
            ),
            consumer_group: env_or_default(
                "STREAM_NORMALIZER_CONSUMER_GROUP",
                "stream-normalizer-v1",
            ),
            source_topics: csv_env_or_default(
                "STREAM_NORMALIZER_SOURCE_TOPICS",
                DEFAULT_SOURCE_TOPICS,
            ),
            features_topic: env_or_default("FEATURES_TOPIC", FEATURES_EVENTS_TOPIC),
            state_topic: env_or_default("STATE_TOPIC", STATE_LATEST_TOPIC),
            dlq_topic: env_or_default("DLQ_TOPIC", DLQ_TOPIC),
            state_output_enabled: bool_env("STREAM_NORMALIZER_STATE_OUTPUT_ENABLED", false),
            health_bind: env_or_default("STREAM_NORMALIZER_HEALTH_BIND", "127.0.0.1"),
            health_port: env_u16("STREAM_NORMALIZER_HEALTH_PORT", 8080),
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
pub struct NormalizedEvent {
    pub entity_id: String,
    pub source_event_id: String,
    pub event_ts: String,
    pub source_topic: String,
    pub mqtt_topic: String,
    pub event_kind: String,
    pub payload_b64: String,
    pub qos: i32,
    pub retain: bool,
    pub raw_json: String,
}

#[derive(Debug, Default)]
pub struct LatestState {
    latest_by_entity: HashMap<String, String>,
}

impl LatestState {
    pub fn accepts(&mut self, event: &NormalizedEvent) -> bool {
        match self.latest_by_entity.get(&event.entity_id) {
            Some(current) if event.event_ts < *current => false,
            _ => {
                self.latest_by_entity
                    .insert(event.entity_id.clone(), event.event_ts.clone());
                true
            }
        }
    }
}

pub fn normalize_record(source_topic: &str, raw_json: &str) -> Option<NormalizedEvent> {
    let record: Value = serde_json::from_str(raw_json).ok()?;
    record.as_object()?;
    let mqtt_topic = string_field(&record, "mqtt_topic").unwrap_or_default();
    let entity_id = string_field(&record, "device_id")
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| infer_entity_id(&mqtt_topic));
    let event_ts = string_field(&record, "timestamp")
        .or_else(|| string_field(&record, "ingested_at"))
        .unwrap_or_default();

    Some(NormalizedEvent {
        entity_id,
        source_event_id: string_field(&record, "event_id").unwrap_or_default(),
        event_ts,
        source_topic: source_topic.to_string(),
        mqtt_topic: mqtt_topic.clone(),
        event_kind: infer_event_kind(source_topic, &mqtt_topic),
        payload_b64: string_field(&record, "payload_b64").unwrap_or_default(),
        qos: record.get("qos").and_then(Value::as_i64).unwrap_or(0) as i32,
        retain: record
            .get("retain")
            .and_then(Value::as_bool)
            .unwrap_or(false),
        raw_json: raw_json.to_string(),
    })
}

pub fn invalid_record_dlq_json(
    source_topic: &str,
    raw_payload: &str,
) -> Result<String, serde_json::Error> {
    serde_json::to_string(&serde_json::json!({
        "timestamp": now_iso(),
        "source": "stream-normalizer",
        "intended_topic": source_topic,
        "source_topic": source_topic,
        "device_id": "unknown",
        "errors": ["record must be a JSON object"],
        "raw_event": {"raw_payload": raw_payload},
    }))
}

pub fn normalized_event_json(event: &NormalizedEvent) -> Result<String, serde_json::Error> {
    serde_json::to_string(event)
}

pub fn infer_entity_id(mqtt_topic: &str) -> String {
    let parts: Vec<_> = mqtt_topic
        .split('/')
        .filter(|part| !part.is_empty())
        .collect();
    let lowered_parts: Vec<_> = parts.iter().map(|part| part.to_ascii_lowercase()).collect();

    for marker in WILDFI_TAG_MARKERS {
        if let Some(idx) = lowered_parts.iter().position(|part| part == marker) {
            if let Some(value) = parts.get(idx + 1) {
                return (*value).to_string();
            }
        }
    }

    for marker in WILDFI_TOPIC_MARKERS {
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

pub fn infer_event_kind(source_topic: &str, mqtt_topic: &str) -> String {
    match source_topic.to_ascii_lowercase().as_str() {
        "raw.sensor" => return "sensor".to_string(),
        "raw.gps" => return "gps".to_string(),
        "raw.image2d.meta" => return "image2d".to_string(),
        "raw.image3d.meta" => return "image3d".to_string(),
        "raw.video2d.meta" => return "video2d".to_string(),
        "raw.video3d.meta" => return "video3d".to_string(),
        _ => {}
    }

    let lowered = mqtt_topic.to_ascii_lowercase();
    let patterns = [
        ("gps", &["gps", "/gnss/"][..]),
        (
            "video3d",
            &["video3d", "/stereo-video/", "/volumetric-video/"][..],
        ),
        ("video2d", &["video2d", "/video/", "/camera-stream/"][..]),
        ("image3d", &["image3d", "/lidar/", "/pointcloud/"][..]),
        ("image2d", &["image2d", "/camera/", "/image/"][..]),
    ];

    patterns
        .iter()
        .find_map(|(kind, items)| {
            items
                .iter()
                .any(|pattern| lowered.contains(pattern))
                .then(|| (*kind).to_string())
        })
        .unwrap_or_else(|| "unknown".to_string())
}

pub fn env_or_default(name: &str, default: &str) -> String {
    std::env::var(name)
        .ok()
        .filter(|value| !value.trim().is_empty())
        .map_or_else(|| default.to_string(), |value| value.trim().to_string())
}

pub fn csv_env_or_default(name: &str, default: &str) -> Vec<String> {
    let value = std::env::var(name).unwrap_or_else(|_| default.to_string());
    let parsed = csv_items(&value);
    if parsed.is_empty() {
        csv_items(default)
    } else {
        parsed
    }
}

pub fn env_u16(name: &str, default: u16) -> u16 {
    std::env::var(name)
        .ok()
        .filter(|value| !value.trim().is_empty())
        .and_then(|value| value.parse::<u16>().ok())
        .unwrap_or(default)
}

pub fn bool_env(name: &str, default: bool) -> bool {
    std::env::var(name).map_or(default, |value| {
        matches!(
            value.trim().to_ascii_lowercase().as_str(),
            "1" | "true" | "yes" | "on"
        )
    })
}

fn csv_items(value: &str) -> Vec<String> {
    value
        .split(',')
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .map(ToString::to_string)
        .collect()
}

fn string_field(record: &Value, field: &str) -> Option<String> {
    record.get(field).map(|value| {
        value
            .as_str()
            .map_or_else(|| value.to_string(), ToString::to_string)
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalizes_raw_gps_record() {
        let raw = r#"{"device_id":"tag-1","event_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","timestamp":"2026-01-01T00:00:00+00:00","mqtt_topic":"wildfi/tags/tag-1/gps","qos":1,"retain":false}"#;

        let event = normalize_record("raw.gps", raw).expect("valid json");

        assert_eq!(event.entity_id, "tag-1");
        assert_eq!(event.source_event_id.len(), 64);
        assert_eq!(event.event_kind, "gps");
        assert_eq!(event.qos, 1);
        assert_eq!(event.raw_json, raw);
    }

    #[test]
    fn infers_wildfi_entity_id() {
        assert_eq!(infer_entity_id("wildfi/tags/WF-001/gps"), "WF-001");
        assert_eq!(infer_entity_id("wildfi/WF-002/environment"), "WF-002");
        assert_eq!(infer_entity_id("/"), "unknown");
    }

    #[test]
    fn drops_invalid_json() {
        assert!(normalize_record("raw.sensor", "{bad json").is_none());
        assert!(normalize_record("raw.sensor", "[]").is_none());
    }

    #[test]
    fn serializes_invalid_record_for_dlq() {
        let event: Value = serde_json::from_str(
            &invalid_record_dlq_json("raw.sensor", "{bad json").expect("dlq json"),
        )
        .expect("valid JSON");

        assert_eq!(event["source"], "stream-normalizer");
        assert_eq!(event["intended_topic"], "raw.sensor");
        assert_eq!(event["raw_event"]["raw_payload"], "{bad json");
    }

    #[test]
    fn latest_state_accepts_newer_events_only() {
        let mut state = LatestState::default();
        let old = NormalizedEvent {
            entity_id: "sensor-1".to_string(),
            source_event_id: "a".repeat(64),
            event_ts: "2026-01-01T00:00:00+00:00".to_string(),
            source_topic: "raw.sensor".to_string(),
            mqtt_topic: "devices/sensor-1/sensor".to_string(),
            event_kind: "sensor".to_string(),
            payload_b64: String::new(),
            qos: 0,
            retain: false,
            raw_json: "{}".to_string(),
        };
        let mut newer = old.clone();
        newer.event_ts = "2026-01-02T00:00:00+00:00".to_string();

        assert!(state.accepts(&newer));
        assert!(!state.accepts(&old));
    }

    #[test]
    fn env_u16_falls_back_for_missing_or_invalid_values() {
        assert_eq!(env_u16("STREAM_NORMALIZER_UNIT_MISSING", 8080), 8080);
    }

    #[test]
    fn state_output_is_disabled_by_default() {
        assert!(!bool_env(
            "STREAM_NORMALIZER_STATE_OUTPUT_UNIT_MISSING",
            false
        ));
    }
}
