use dealiot_mqtt_kafka_bridge::{build_event, route_event, BridgeConfig, BridgeError, MqttMessage};
use log::{error, info, warn};
use rdkafka::config::ClientConfig;
use rdkafka::producer::{FutureProducer, FutureRecord, Producer};
use rdkafka::util::Timeout;
use rumqttc::{AsyncClient, Event, Incoming, MqttOptions, QoS, SubAck, SubscribeReasonCode};
use std::fs;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};
use tiny_http::{Header, Response, Server, StatusCode};

const KAFKA_DELIVERY_BUCKETS: [(u64, &str); 11] = [
    (5_000, "0.005"),
    (10_000, "0.01"),
    (25_000, "0.025"),
    (50_000, "0.05"),
    (100_000, "0.1"),
    (250_000, "0.25"),
    (500_000, "0.5"),
    (1_000_000, "1"),
    (2_500_000, "2.5"),
    (5_000_000, "5"),
    (10_000_000, "10"),
];
const KAFKA_METADATA_TIMEOUT: Duration = Duration::from_secs(5);
const KAFKA_HEALTH_INTERVAL: Duration = Duration::from_secs(15);
const KAFKA_QUEUE_TIMEOUT: Duration = Duration::from_secs(5);
const KAFKA_DELIVERY_TIMEOUT_MS: &str = "30000";
const KAFKA_SOCKET_TIMEOUT_MS: &str = "10000";

struct DurationHistogram {
    buckets: [AtomicU64; KAFKA_DELIVERY_BUCKETS.len()],
    count: AtomicU64,
    sum_microseconds: AtomicU64,
}

impl Default for DurationHistogram {
    fn default() -> Self {
        Self {
            buckets: std::array::from_fn(|_| AtomicU64::new(0)),
            count: AtomicU64::new(0),
            sum_microseconds: AtomicU64::new(0),
        }
    }
}

impl DurationHistogram {
    fn observe(&self, duration: Duration) {
        let microseconds = duration.as_micros().min(u128::from(u64::MAX)) as u64;
        self.count.fetch_add(1, Ordering::Relaxed);
        self.sum_microseconds
            .fetch_add(microseconds, Ordering::Relaxed);
        for (index, (upper_bound, _)) in KAFKA_DELIVERY_BUCKETS.iter().enumerate() {
            if microseconds <= *upper_bound {
                self.buckets[index].fetch_add(1, Ordering::Relaxed);
            }
        }
    }
}

#[derive(Default)]
struct BridgeMetrics {
    ready: AtomicBool,
    mqtt_subscriptions_ready: AtomicBool,
    kafka_ready: AtomicBool,
    received_total: AtomicU64,
    forwarded_total: AtomicU64,
    dlq_total: AtomicU64,
    errors_total: AtomicU64,
    kafka_metadata_errors_total: AtomicU64,
    kafka_delivery_duration: DurationHistogram,
}

impl BridgeMetrics {
    fn reset_readiness(&self) {
        self.mqtt_subscriptions_ready
            .store(false, Ordering::Relaxed);
        self.kafka_ready.store(false, Ordering::Relaxed);
        self.ready.store(false, Ordering::Relaxed);
    }

    fn update_readiness(&self) {
        self.ready.store(
            self.mqtt_subscriptions_ready.load(Ordering::Relaxed)
                && self.kafka_ready.load(Ordering::Relaxed),
            Ordering::Relaxed,
        );
    }

    fn set_mqtt_subscriptions_ready(&self, ready: bool) {
        self.mqtt_subscriptions_ready
            .store(ready, Ordering::Relaxed);
        self.update_readiness();
    }

    fn set_kafka_ready(&self, ready: bool) {
        let was_ready = self.kafka_ready.swap(ready, Ordering::Relaxed);
        if was_ready && !ready {
            self.errors_total.fetch_add(1, Ordering::Relaxed);
            self.kafka_metadata_errors_total
                .fetch_add(1, Ordering::Relaxed);
        }
        self.update_readiness();
    }

    fn render_prometheus(&self) -> String {
        let count = self.kafka_delivery_duration.count.load(Ordering::Relaxed);
        let sum_seconds = self
            .kafka_delivery_duration
            .sum_microseconds
            .load(Ordering::Relaxed) as f64
            / 1_000_000.0;
        let mut output = format!(
            concat!(
                "# HELP dealiot_bridge_ready Whether MQTT subscriptions and the Kafka control path are ready.\n",
                "# TYPE dealiot_bridge_ready gauge\n",
                "dealiot_bridge_ready {}\n",
                "# HELP dealiot_bridge_mqtt_subscriptions_ready Whether all configured MQTT subscriptions are acknowledged.\n",
                "# TYPE dealiot_bridge_mqtt_subscriptions_ready gauge\n",
                "dealiot_bridge_mqtt_subscriptions_ready {}\n",
                "# HELP dealiot_bridge_kafka_ready Whether the most recent bounded Kafka metadata check succeeded.\n",
                "# TYPE dealiot_bridge_kafka_ready gauge\n",
                "dealiot_bridge_kafka_ready {}\n",
                "# HELP dealiot_bridge_received_total MQTT publish deliveries received, including broker redeliveries.\n",
                "# TYPE dealiot_bridge_received_total counter\n",
                "dealiot_bridge_received_total {}\n",
                "# HELP dealiot_bridge_forwarded_total MQTT deliveries durably written to Kafka and acknowledged to MQTT.\n",
                "# TYPE dealiot_bridge_forwarded_total counter\n",
                "dealiot_bridge_forwarded_total {}\n",
                "# HELP dealiot_bridge_dlq_total Durably forwarded messages routed to the invalid-event DLQ.\n",
                "# TYPE dealiot_bridge_dlq_total counter\n",
                "dealiot_bridge_dlq_total {}\n",
                "# HELP dealiot_bridge_errors_total Bridge reconnect, delivery or Kafka metadata failures.\n",
                "# TYPE dealiot_bridge_errors_total counter\n",
                "dealiot_bridge_errors_total {}\n",
                "# HELP dealiot_bridge_kafka_metadata_errors_total Kafka metadata health transitions from ready to unavailable.\n",
                "# TYPE dealiot_bridge_kafka_metadata_errors_total counter\n",
                "dealiot_bridge_kafka_metadata_errors_total {}\n",
                "# HELP dealiot_bridge_kafka_delivery_duration_seconds Kafka produce acknowledgement latency.\n",
                "# TYPE dealiot_bridge_kafka_delivery_duration_seconds histogram\n"
            ),
            u8::from(self.ready.load(Ordering::Relaxed)),
            u8::from(self.mqtt_subscriptions_ready.load(Ordering::Relaxed)),
            u8::from(self.kafka_ready.load(Ordering::Relaxed)),
            self.received_total.load(Ordering::Relaxed),
            self.forwarded_total.load(Ordering::Relaxed),
            self.dlq_total.load(Ordering::Relaxed),
            self.errors_total.load(Ordering::Relaxed),
            self.kafka_metadata_errors_total.load(Ordering::Relaxed),
        );
        for (index, (_, label)) in KAFKA_DELIVERY_BUCKETS.iter().enumerate() {
            output.push_str(&format!(
                "dealiot_bridge_kafka_delivery_duration_seconds_bucket{{le=\"{label}\"}} {}\n",
                self.kafka_delivery_duration.buckets[index].load(Ordering::Relaxed),
            ));
        }
        output.push_str(&format!(
            concat!(
                "dealiot_bridge_kafka_delivery_duration_seconds_bucket{{le=\"+Inf\"}} {count}\n",
                "dealiot_bridge_kafka_delivery_duration_seconds_sum {sum_seconds:.6}\n",
                "dealiot_bridge_kafka_delivery_duration_seconds_count {count}\n"
            ),
            count = count,
            sum_seconds = sum_seconds,
        ));
        output
    }
}

#[tokio::main]
async fn main() -> Result<(), BridgeError> {
    env_logger::init();
    let config = BridgeConfig::from_env()?;
    validate_auth_config(&config)?;
    let metrics = Arc::new(BridgeMetrics::default());
    start_health_server(
        config.bridge_health_bind.clone(),
        config.bridge_health_port,
        Arc::clone(&metrics),
    );

    loop {
        metrics.reset_readiness();
        match run_bridge(&config, Arc::clone(&metrics)).await {
            Ok(()) => return Ok(()),
            Err(error) => {
                metrics.reset_readiness();
                metrics.errors_total.fetch_add(1, Ordering::Relaxed);
                error!("Bridge error; retry in 5s: {error}");
                tokio::time::sleep(Duration::from_secs(5)).await;
            }
        }
    }
}

async fn run_bridge(config: &BridgeConfig, metrics: Arc<BridgeMetrics>) -> Result<(), BridgeError> {
    let producer = kafka_producer(config)?;
    producer
        .client()
        .fetch_metadata(None, Timeout::After(KAFKA_METADATA_TIMEOUT))
        .map_err(|error| BridgeError::Config(format!("Kafka metadata check failed: {error}")))?;
    metrics.set_kafka_ready(true);
    let mut mqtt_options = MqttOptions::new(
        config.mqtt_client_id.clone(),
        (config.mqtt_host.clone(), config.mqtt_port),
    );
    mqtt_options
        .set_keep_alive(30)
        .set_clean_session(config.mqtt_clean_session)
        .set_manual_acks(true);

    if let (Some(username), Some(password)) = (&config.mqtt_username, &config.mqtt_password) {
        mqtt_options.set_credentials(username.clone(), password.clone());
    }

    if config.mqtt_tls_enabled {
        configure_mqtt_tls(config, &mut mqtt_options)?;
    }

    let (client, mut eventloop) = AsyncClient::builder(mqtt_options).capacity(100).build();
    for topic in &config.mqtt_topics {
        client
            .subscribe(topic.clone(), QoS::AtLeastOnce)
            .await
            .map_err(|error| BridgeError::Config(format!("MQTT subscribe failed: {error}")))?;
        info!("Subscribed to {topic}");
    }

    let shutdown = shutdown_signal();
    tokio::pin!(shutdown);
    let mut pending_subscriptions = config.mqtt_topics.len();
    let mut kafka_health_interval = tokio::time::interval(KAFKA_HEALTH_INTERVAL);
    kafka_health_interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
    kafka_health_interval.tick().await;
    loop {
        tokio::select! {
            _ = &mut shutdown => {
                metrics.reset_readiness();
                let _ = client.disconnect().await;
                producer.flush(Timeout::After(Duration::from_secs(10))).map_err(|error| {
                    BridgeError::Config(format!("Kafka flush during shutdown failed: {error}"))
                })?;
                info!("Graceful shutdown completed");
                return Ok(());
            }
            _ = kafka_health_interval.tick() => {
                let health_producer = producer.clone();
                let check = tokio::task::spawn_blocking(move || {
                    health_producer
                        .client()
                        .fetch_metadata(None, Timeout::After(KAFKA_METADATA_TIMEOUT))
                        .map(|_| ())
                        .map_err(|error| error.to_string())
                });
                match tokio::time::timeout(KAFKA_METADATA_TIMEOUT + Duration::from_secs(1), check).await {
                    Ok(Ok(Ok(_))) => {
                        let recovered = !metrics.kafka_ready.load(Ordering::Relaxed);
                        metrics.set_kafka_ready(true);
                        if recovered {
                            info!("Kafka metadata health check recovered");
                        }
                    }
                    Ok(Ok(Err(error))) => {
                        metrics.set_kafka_ready(false);
                        warn!("Kafka metadata health check failed: {error}");
                    }
                    Ok(Err(error)) => {
                        metrics.set_kafka_ready(false);
                        warn!("Kafka metadata health task failed: {error}");
                    }
                    Err(_) => {
                        metrics.set_kafka_ready(false);
                        warn!("Kafka metadata health check exceeded its bounded timeout");
                    }
                }
            }
            event = eventloop.poll() => match event {
            Ok(Event::Incoming(Incoming::Publish(publish))) => {
                metrics.received_total.fetch_add(1, Ordering::Relaxed);
                let msg = MqttMessage {
                    topic: publish.topic.clone(),
                    payload: publish.payload.to_vec(),
                    qos: qos_number(publish.qos),
                    retain: publish.retain,
                };
                let built = build_event(&msg, config);
                let (send_topic, send_event) = route_event(&built.topic, built.event);
                let payload = serde_json::to_vec(&send_event)?;
                let key = built.key;
                let delivery_started_at = Instant::now();
                producer
                    .send(
                        FutureRecord::to(&send_topic).key(&key).payload(&payload),
                        Timeout::After(KAFKA_QUEUE_TIMEOUT),
                    )
                    .await
                    .map_err(|(error, _)| {
                        BridgeError::Config(format!("Kafka send failed: {error}"))
                    })?;
                metrics
                    .kafka_delivery_duration
                    .observe(delivery_started_at.elapsed());
                client.ack(&publish).await.map_err(|error| {
                    BridgeError::Config(format!("MQTT acknowledgement failed: {error}"))
                })?;
                metrics.forwarded_total.fetch_add(1, Ordering::Relaxed);
                if send_topic == dealiot_event_contracts::DLQ_TOPIC {
                    metrics.dlq_total.fetch_add(1, Ordering::Relaxed);
                }
                info!("Forwarded MQTT message to Kafka topic={send_topic}");
            }
            Ok(Event::Incoming(Incoming::SubAck(suback))) => {
                if handle_subscription_ack(&suback, &mut pending_subscriptions, &metrics)? {
                    info!("Bridge is ready; all MQTT subscriptions and Kafka metadata checks succeeded");
                }
            }
            Ok(_) => {}
            Err(error) => {
                return Err(BridgeError::Config(format!(
                    "MQTT event loop failed: {error}"
                )))
            }
            }
        }
    }
}

fn handle_subscription_ack(
    suback: &SubAck,
    pending_subscriptions: &mut usize,
    metrics: &BridgeMetrics,
) -> Result<bool, BridgeError> {
    // run_bridge queues one topic per SUBSCRIBE request. MQTT requires the matching SUBACK to
    // contain exactly one reason code; accepting a batched or unsolicited response would hide a
    // protocol/client bookkeeping error and could mark subscriptions ready prematurely.
    let accepted = suback.return_codes.len() == 1
        && suback
            .return_codes
            .iter()
            .all(|code| matches!(code, SubscribeReasonCode::Success(QoS::AtLeastOnce)));
    if !accepted {
        metrics.set_mqtt_subscriptions_ready(false);
        return Err(BridgeError::Config(format!(
            "MQTT QoS 1 subscription rejected or downgraded pkid={} return_codes={:?}",
            suback.pkid, suback.return_codes
        )));
    }

    *pending_subscriptions = pending_subscriptions.saturating_sub(1);
    let all_subscriptions_ready = *pending_subscriptions == 0;
    if all_subscriptions_ready {
        metrics.set_mqtt_subscriptions_ready(true);
    }
    Ok(all_subscriptions_ready)
}

async fn shutdown_signal() {
    #[cfg(unix)]
    {
        use tokio::signal::unix::{signal, SignalKind};

        let mut terminate = signal(SignalKind::terminate()).expect("SIGTERM handler");
        tokio::select! {
            _ = tokio::signal::ctrl_c() => {},
            _ = terminate.recv() => {},
        }
    }
    #[cfg(not(unix))]
    {
        let _ = tokio::signal::ctrl_c().await;
    }
}

fn kafka_producer(config: &BridgeConfig) -> Result<FutureProducer, BridgeError> {
    kafka_client_config(config)?
        .create()
        .map_err(|error| BridgeError::Config(format!("Kafka producer init failed: {error}")))
}

fn kafka_client_config(config: &BridgeConfig) -> Result<ClientConfig, BridgeError> {
    let mut client_config = base_kafka_client_config(config);
    apply_kafka_security_config(&mut client_config)?;
    Ok(client_config)
}

fn base_kafka_client_config(config: &BridgeConfig) -> ClientConfig {
    let mut client_config = ClientConfig::new();
    client_config
        .set("bootstrap.servers", config.kafka_bootstrap_servers.as_str())
        .set("acks", "all")
        .set("enable.idempotence", "true")
        .set("retries", "10")
        .set("linger.ms", "50")
        .set("batch.size", "131072")
        .set("compression.type", "lz4")
        .set("max.in.flight.requests.per.connection", "1")
        .set("delivery.timeout.ms", KAFKA_DELIVERY_TIMEOUT_MS)
        .set("message.timeout.ms", KAFKA_DELIVERY_TIMEOUT_MS)
        .set("socket.timeout.ms", KAFKA_SOCKET_TIMEOUT_MS);

    client_config
}

fn apply_kafka_security_config(client_config: &mut ClientConfig) -> Result<(), BridgeError> {
    let security_protocol =
        std::env::var("KAFKA_SECURITY_PROTOCOL").unwrap_or_else(|_| "PLAINTEXT".to_string());
    client_config.set("security.protocol", security_protocol.trim());

    if security_protocol.starts_with("SASL_") {
        let username = std::env::var("KAFKA_SASL_USERNAME").ok();
        let password = dealiot_mqtt_kafka_bridge::env_or_secret_file("KAFKA_SASL_PASSWORD")?;
        let (Some(username), Some(password)) = (username, password) else {
            return Err(BridgeError::Config(
                "KAFKA_SASL_USERNAME and KAFKA_SASL_PASSWORD must both be set when Kafka SASL is enabled"
                    .to_string(),
            ));
        };
        client_config
            .set(
                "sasl.mechanisms",
                std::env::var("KAFKA_SASL_MECHANISM")
                    .unwrap_or_else(|_| "SCRAM-SHA-512".to_string()),
            )
            .set("sasl.username", username)
            .set("sasl.password", password);
    }

    if security_protocol.contains("SSL") {
        set_optional(client_config, "ssl.ca.location", "KAFKA_SSL_CAFILE");
        set_optional(
            client_config,
            "ssl.certificate.location",
            "KAFKA_SSL_CERTFILE",
        );
        set_optional(client_config, "ssl.key.location", "KAFKA_SSL_KEYFILE");
        if !dealiot_mqtt_kafka_bridge::bool_env("KAFKA_SSL_CHECK_HOSTNAME", true) {
            client_config.set("enable.ssl.certificate.verification", "false");
        }
    }

    Ok(())
}

fn set_optional(client_config: &mut ClientConfig, property: &str, env_name: &str) {
    if let Ok(value) = std::env::var(env_name) {
        if !value.is_empty() {
            client_config.set(property, value);
        }
    }
}

fn configure_mqtt_tls(
    config: &BridgeConfig,
    mqtt_options: &mut MqttOptions,
) -> Result<(), BridgeError> {
    if config.mqtt_tls_insecure_skip_verify {
        warn!(
            "MQTT_TLS_INSECURE_SKIP_VERIFY is not supported by the Rust bridge; using verified TLS"
        );
    }

    let client_auth = match (&config.mqtt_tls_cert_file, &config.mqtt_tls_key_file) {
        (Some(cert), Some(key)) => Some((fs::read(cert)?, fs::read(key)?)),
        (None, None) => None,
        _ => return Err(BridgeError::Config(
            "MQTT_TLS_CERT_FILE and MQTT_TLS_KEY_FILE must both be set for MQTT client TLS auth"
                .to_string(),
        )),
    };

    let tls_config = if let Some(ca_file) = &config.mqtt_tls_ca_file {
        let ca = fs::read(ca_file)?;
        rumqttc::TlsConfiguration::Simple {
            ca,
            alpn: None,
            client_auth,
        }
    } else if client_auth.is_none() {
        rumqttc::TlsConfiguration::default()
    } else {
        return Err(BridgeError::Config(
            "MQTT_TLS_CA_FILE must be set when MQTT client TLS auth is enabled".to_string(),
        ));
    };

    mqtt_options.set_transport(rumqttc::Transport::tls_with_config(tls_config));
    Ok(())
}

fn validate_auth_config(config: &BridgeConfig) -> Result<(), BridgeError> {
    if config.mqtt_username.is_some() != config.mqtt_password.is_some() {
        return Err(BridgeError::Config(
            "MQTT_USERNAME and MQTT_PASSWORD must both be set when MQTT auth is enabled"
                .to_string(),
        ));
    }
    Ok(())
}

fn start_health_server(bind: String, port: u16, metrics: Arc<BridgeMetrics>) {
    thread::spawn(move || {
        let server = match Server::http((bind.as_str(), port)) {
            Ok(server) => server,
            Err(error) => {
                error!("health server failed to bind: {error}");
                return;
            }
        };

        for request in server.incoming_requests() {
            if request.url() == "/healthz" {
                let response = Response::from_string(r#"{"status":"alive"}"#)
                    .with_status_code(StatusCode(200))
                    .with_header(
                        Header::from_bytes(&b"Content-Type"[..], &b"application/json"[..])
                            .expect("static header is valid"),
                    );
                let _ = request.respond(response);
            } else if request.url() == "/readyz" {
                let is_ready = metrics.ready.load(Ordering::Relaxed);
                let status = if is_ready {
                    StatusCode(200)
                } else {
                    StatusCode(503)
                };
                let body = if is_ready {
                    r#"{"status":"ready"}"#
                } else {
                    r#"{"status":"not_ready"}"#
                };
                let response = Response::from_string(body)
                    .with_status_code(status)
                    .with_header(
                        Header::from_bytes(&b"Content-Type"[..], &b"application/json"[..])
                            .expect("static header is valid"),
                    );
                let _ = request.respond(response);
            } else if request.url() == "/metrics" {
                let body = metrics.render_prometheus();
                let response = Response::from_string(body)
                    .with_status_code(StatusCode(200))
                    .with_header(
                        Header::from_bytes(&b"Content-Type"[..], &b"text/plain; version=0.0.4"[..])
                            .expect("static header is valid"),
                    );
                let _ = request.respond(response);
            } else {
                let _ = request.respond(Response::empty(StatusCode(404)));
            }
        }
    });
}

fn qos_number(qos: QoS) -> i32 {
    match qos {
        QoS::AtMostOnce => 0,
        QoS::AtLeastOnce => 1,
        QoS::ExactlyOnce => 2,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use dealiot_event_contracts::RAW_SENSOR_TOPIC;
    use std::path::Path;
    use tempfile::tempdir;

    fn test_config() -> BridgeConfig {
        BridgeConfig {
            mqtt_client_id: "mqtt-kafka-bridge-test".to_string(),
            mqtt_clean_session: false,
            mqtt_host: "localhost".to_string(),
            mqtt_port: 8883,
            mqtt_username: None,
            mqtt_password: None,
            mqtt_tls_enabled: true,
            mqtt_tls_ca_file: None,
            mqtt_tls_cert_file: None,
            mqtt_tls_key_file: None,
            mqtt_tls_insecure_skip_verify: false,
            mqtt_topics: vec!["devices/#".to_string()],
            wildfi_topic_prefixes: vec!["wildfi".to_string(), "wild-fi".to_string()],
            kafka_bootstrap_servers: "localhost:9092".to_string(),
            default_kafka_topic: RAW_SENSOR_TOPIC.to_string(),
            bridge_health_port: 8080,
            bridge_health_bind: "127.0.0.1".to_string(),
        }
    }

    fn mqtt_options() -> MqttOptions {
        MqttOptions::new("unit-test", ("localhost", 8883))
    }

    fn write_tls_file(directory: &Path, name: &str) -> String {
        let path = directory.join(name);
        fs::write(&path, b"test pem bytes").expect("test TLS file can be written");
        path.to_string_lossy().into_owned()
    }

    #[test]
    fn mqtt_tls_uses_platform_roots_without_explicit_ca() {
        let config = test_config();
        let mut options = mqtt_options();

        configure_mqtt_tls(&config, &mut options).expect("server-only TLS should be valid");
    }

    #[test]
    fn mqtt_tls_requires_client_cert_and_key_together() {
        let temp = tempdir().expect("tempdir");
        let cert = write_tls_file(temp.path(), "client.pem");
        let mut config = test_config();
        config.mqtt_tls_cert_file = Some(cert);
        let mut options = mqtt_options();

        let error = configure_mqtt_tls(&config, &mut options).expect_err("missing key fails");

        assert!(error
            .to_string()
            .contains("MQTT_TLS_CERT_FILE and MQTT_TLS_KEY_FILE must both be set"));
    }

    #[test]
    fn mqtt_tls_requires_ca_for_client_certificate_auth() {
        let temp = tempdir().expect("tempdir");
        let mut config = test_config();
        config.mqtt_tls_cert_file = Some(write_tls_file(temp.path(), "client.pem"));
        config.mqtt_tls_key_file = Some(write_tls_file(temp.path(), "client.key"));
        let mut options = mqtt_options();

        let error =
            configure_mqtt_tls(&config, &mut options).expect_err("client auth without CA fails");

        assert!(error
            .to_string()
            .contains("MQTT_TLS_CA_FILE must be set when MQTT client TLS auth is enabled"));
    }

    #[test]
    fn mqtt_tls_accepts_ca_with_client_certificate_auth() {
        let temp = tempdir().expect("tempdir");
        let mut config = test_config();
        config.mqtt_tls_ca_file = Some(write_tls_file(temp.path(), "ca.pem"));
        config.mqtt_tls_cert_file = Some(write_tls_file(temp.path(), "client.pem"));
        config.mqtt_tls_key_file = Some(write_tls_file(temp.path(), "client.key"));
        let mut options = mqtt_options();

        configure_mqtt_tls(&config, &mut options).expect("complete client TLS auth should work");
    }

    #[test]
    fn bridge_metrics_expose_durable_delivery_denominator_and_latency_histogram() {
        let metrics = BridgeMetrics::default();
        metrics.received_total.fetch_add(2, Ordering::Relaxed);
        metrics.forwarded_total.fetch_add(1, Ordering::Relaxed);
        metrics
            .kafka_delivery_duration
            .observe(Duration::from_millis(75));

        let output = metrics.render_prometheus();

        assert!(output.contains("dealiot_bridge_received_total 2"));
        assert!(output.contains("dealiot_bridge_forwarded_total 1"));
        assert!(
            output.contains("dealiot_bridge_kafka_delivery_duration_seconds_bucket{le=\"0.1\"} 1")
        );
        assert!(
            output.contains("dealiot_bridge_kafka_delivery_duration_seconds_bucket{le=\"0.05\"} 0")
        );
        assert!(output.contains("dealiot_bridge_kafka_delivery_duration_seconds_count 1"));
    }

    #[test]
    fn bridge_readiness_tracks_both_dependencies_and_metadata_failures() {
        let metrics = BridgeMetrics::default();

        metrics.set_mqtt_subscriptions_ready(true);
        assert!(!metrics.ready.load(Ordering::Relaxed));

        metrics.set_kafka_ready(true);
        assert!(metrics.ready.load(Ordering::Relaxed));

        metrics.set_kafka_ready(false);
        metrics.set_kafka_ready(false);
        assert!(!metrics.ready.load(Ordering::Relaxed));
        assert_eq!(metrics.errors_total.load(Ordering::Relaxed), 1);
        assert_eq!(
            metrics.kafka_metadata_errors_total.load(Ordering::Relaxed),
            1
        );

        metrics.reset_readiness();
        assert_eq!(metrics.errors_total.load(Ordering::Relaxed), 1);
    }

    #[test]
    fn kafka_producer_configuration_bounds_queue_delivery_and_metadata_checks() {
        let config = base_kafka_client_config(&test_config());

        assert_eq!(
            config.get("delivery.timeout.ms"),
            Some(KAFKA_DELIVERY_TIMEOUT_MS)
        );
        assert_eq!(
            config.get("message.timeout.ms"),
            Some(KAFKA_DELIVERY_TIMEOUT_MS)
        );
        assert_eq!(
            config.get("socket.timeout.ms"),
            Some(KAFKA_SOCKET_TIMEOUT_MS)
        );
        assert_eq!(KAFKA_QUEUE_TIMEOUT, Duration::from_secs(5));
        assert_eq!(KAFKA_METADATA_TIMEOUT, Duration::from_secs(5));
        assert_eq!(KAFKA_HEALTH_INTERVAL, Duration::from_secs(15));
    }

    #[test]
    fn mqtt_subscription_rejection_cannot_leave_the_bridge_ready() {
        let metrics = BridgeMetrics::default();
        metrics.set_kafka_ready(true);
        metrics.set_mqtt_subscriptions_ready(true);
        let mut pending_subscriptions = 1;
        let rejected = SubAck::new(42, vec![SubscribeReasonCode::Failure]);

        let error = handle_subscription_ack(&rejected, &mut pending_subscriptions, &metrics)
            .expect_err("a rejected MQTT subscription must fail the bridge loop");

        assert!(error
            .to_string()
            .contains("MQTT QoS 1 subscription rejected or downgraded"));
        assert_eq!(pending_subscriptions, 1);
        assert!(!metrics.mqtt_subscriptions_ready.load(Ordering::Relaxed));
        assert!(!metrics.ready.load(Ordering::Relaxed));
    }

    #[test]
    fn mqtt_subscription_qos_downgrade_is_rejected() {
        let metrics = BridgeMetrics::default();
        metrics.set_kafka_ready(true);
        let mut pending_subscriptions = 1;
        let downgraded = SubAck::new(43, vec![SubscribeReasonCode::Success(QoS::AtMostOnce)]);

        handle_subscription_ack(&downgraded, &mut pending_subscriptions, &metrics)
            .expect_err("a QoS 0 grant must not satisfy the QoS 1 ingestion contract");

        assert_eq!(pending_subscriptions, 1);
        assert!(!metrics.ready.load(Ordering::Relaxed));
    }

    #[test]
    fn mqtt_subscription_ack_must_match_one_subscribe_request() {
        let metrics = BridgeMetrics::default();
        metrics.set_kafka_ready(true);
        let mut pending_subscriptions = 2;
        let unexpected_batch = SubAck::new(
            44,
            vec![
                SubscribeReasonCode::Success(QoS::AtLeastOnce),
                SubscribeReasonCode::Success(QoS::AtLeastOnce),
            ],
        );

        handle_subscription_ack(&unexpected_batch, &mut pending_subscriptions, &metrics)
            .expect_err("one SUBSCRIBE request must receive exactly one return code");

        assert_eq!(pending_subscriptions, 2);
        assert!(!metrics.ready.load(Ordering::Relaxed));
    }
}
