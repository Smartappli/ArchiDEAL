use dealiot_mqtt_kafka_bridge::{build_event, route_event, BridgeConfig, BridgeError, MqttMessage};
use log::{error, info, warn};
use rdkafka::config::ClientConfig;
use rdkafka::producer::{FutureProducer, FutureRecord, Producer};
use rdkafka::util::Timeout;
use rumqttc::{AsyncClient, Event, Incoming, MqttOptions, QoS};
use std::fs;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;
use tiny_http::{Header, Response, Server, StatusCode};

#[derive(Default)]
struct BridgeMetrics {
    ready: AtomicBool,
    forwarded_total: AtomicU64,
    dlq_total: AtomicU64,
    errors_total: AtomicU64,
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
        metrics.ready.store(false, Ordering::Relaxed);
        match run_bridge(&config, Arc::clone(&metrics)).await {
            Ok(()) => return Ok(()),
            Err(error) => {
                metrics.ready.store(false, Ordering::Relaxed);
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
        .fetch_metadata(None, Timeout::After(Duration::from_secs(10)))
        .map_err(|error| BridgeError::Config(format!("Kafka metadata check failed: {error}")))?;
    let mut mqtt_options = MqttOptions::new(
        config.mqtt_client_id.clone(),
        config.mqtt_host.clone(),
        config.mqtt_port,
    );
    mqtt_options
        .set_keep_alive(Duration::from_secs(30))
        .set_clean_session(config.mqtt_clean_session)
        .set_manual_acks(true);

    if let (Some(username), Some(password)) = (&config.mqtt_username, &config.mqtt_password) {
        mqtt_options.set_credentials(username.clone(), password.clone());
    }

    if config.mqtt_tls_enabled {
        configure_mqtt_tls(config, &mut mqtt_options)?;
    }

    let (client, mut eventloop) = AsyncClient::new(mqtt_options, 100);
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
    loop {
        tokio::select! {
            _ = &mut shutdown => {
                metrics.ready.store(false, Ordering::Relaxed);
                let _ = client.disconnect().await;
                producer.flush(Timeout::After(Duration::from_secs(10))).map_err(|error| {
                    BridgeError::Config(format!("Kafka flush during shutdown failed: {error}"))
                })?;
                info!("Graceful shutdown completed");
                return Ok(());
            }
            event = eventloop.poll() => match event {
            Ok(Event::Incoming(Incoming::Publish(publish))) => {
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
                producer
                    .send(
                        FutureRecord::to(&send_topic).key(&key).payload(&payload),
                        Timeout::Never,
                    )
                    .await
                    .map_err(|(error, _)| {
                        BridgeError::Config(format!("Kafka send failed: {error}"))
                    })?;
                client.ack(&publish).await.map_err(|error| {
                    BridgeError::Config(format!("MQTT acknowledgement failed: {error}"))
                })?;
                metrics.forwarded_total.fetch_add(1, Ordering::Relaxed);
                if send_topic == dealiot_event_contracts::DLQ_TOPIC {
                    metrics.dlq_total.fetch_add(1, Ordering::Relaxed);
                }
                info!("Forwarded MQTT message to Kafka topic={send_topic}");
            }
            Ok(Event::Incoming(Incoming::SubAck(_))) => {
                pending_subscriptions = pending_subscriptions.saturating_sub(1);
                if pending_subscriptions == 0 {
                    metrics.ready.store(true, Ordering::Relaxed);
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
    let mut client_config = ClientConfig::new();
    client_config
        .set("bootstrap.servers", config.kafka_bootstrap_servers.as_str())
        .set("acks", "all")
        .set("enable.idempotence", "true")
        .set("retries", "10")
        .set("linger.ms", "50")
        .set("batch.size", "131072")
        .set("compression.type", "lz4")
        .set("max.in.flight.requests.per.connection", "1");

    apply_kafka_security_config(&mut client_config)?;
    client_config
        .create()
        .map_err(|error| BridgeError::Config(format!("Kafka producer init failed: {error}")))
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
                let body = format!(
                    concat!(
                        "# TYPE dealiot_bridge_ready gauge\n",
                        "dealiot_bridge_ready {}\n",
                        "# TYPE dealiot_bridge_forwarded_total counter\n",
                        "dealiot_bridge_forwarded_total {}\n",
                        "# TYPE dealiot_bridge_dlq_total counter\n",
                        "dealiot_bridge_dlq_total {}\n",
                        "# TYPE dealiot_bridge_errors_total counter\n",
                        "dealiot_bridge_errors_total {}\n"
                    ),
                    u8::from(metrics.ready.load(Ordering::Relaxed)),
                    metrics.forwarded_total.load(Ordering::Relaxed),
                    metrics.dlq_total.load(Ordering::Relaxed),
                    metrics.errors_total.load(Ordering::Relaxed),
                );
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
        MqttOptions::new("unit-test", "localhost", 8883)
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
}
