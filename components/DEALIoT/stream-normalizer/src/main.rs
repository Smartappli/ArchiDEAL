use dealiot_stream_normalizer::{
    invalid_record_dlq_json, normalize_record, normalized_event_json, LatestState,
    NormalizerConfig,
};
use log::{error, info};
use rdkafka::config::ClientConfig;
use rdkafka::consumer::{CommitMode, Consumer, StreamConsumer};
use rdkafka::message::Message;
use rdkafka::producer::{FutureProducer, FutureRecord};
use rdkafka::util::Timeout;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::Duration;
use thiserror::Error;
use tiny_http::{Header, Response, Server, StatusCode};

#[derive(Debug, Error)]
enum NormalizerError {
    #[error("{0}")]
    Config(String),
    #[error(transparent)]
    Kafka(#[from] rdkafka::error::KafkaError),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
}

#[derive(Default)]
struct NormalizerMetrics {
    ready: AtomicBool,
    processed_total: AtomicU64,
    committed_total: AtomicU64,
    state_updates_total: AtomicU64,
    errors_total: AtomicU64,
}

#[tokio::main]
async fn main() -> Result<(), NormalizerError> {
    env_logger::init();
    let config = NormalizerConfig::from_env();
    let metrics = Arc::new(NormalizerMetrics::default());
    start_health_server(
        config.health_bind.clone(),
        config.health_port,
        Arc::clone(&metrics),
    );
    run(config, metrics).await
}

async fn run(
    config: NormalizerConfig,
    metrics: Arc<NormalizerMetrics>,
) -> Result<(), NormalizerError> {
    let consumer = kafka_consumer(&config)?;
    let producer = kafka_producer(&config)?;
    let topics: Vec<_> = config.source_topics.iter().map(String::as_str).collect();
    consumer.subscribe(&topics)?;
    consumer.fetch_metadata(None, Timeout::After(Duration::from_secs(10)))?;
    metrics.ready.store(true, Ordering::Relaxed);
    info!(
        "Kafka is reachable; subscribed to source topics: {}",
        config.source_topics.join(",")
    );

    let mut latest = LatestState::default();
    let mut readiness_interval = tokio::time::interval(Duration::from_secs(10));
    readiness_interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);

    let shutdown = shutdown_signal();
    tokio::pin!(shutdown);
    loop {
        tokio::select! {
            message = consumer.recv() => {
                let message = message?;
                let source_topic = message.topic().to_string();
                let payload = match message.payload_view::<str>() {
                    Some(Ok(payload)) => payload,
                    Some(Err(error)) => {
                        metrics.errors_total.fetch_add(1, Ordering::Relaxed);
                        error!("Skipping non-UTF8 Kafka payload from {source_topic}: {error}");
                        send_dlq_event(
                            &producer,
                            &config.dlq_topic,
                            &source_topic,
                            "payload is not valid UTF-8",
                            r#"{"payload_encoding":"non-utf8"}"#,
                        )
                        .await?;
                        consumer.commit_message(&message, CommitMode::Sync)?;
                        metrics.committed_total.fetch_add(1, Ordering::Relaxed);
                        continue;
                    }
                    None => continue,
                };

                let Some(event) = normalize_record(&source_topic, payload) else {
                    metrics.errors_total.fetch_add(1, Ordering::Relaxed);
                    let dlq_event = invalid_record_dlq_json(&source_topic, payload)?;
                    producer
                        .send(
                            FutureRecord::to(&config.dlq_topic).payload(&dlq_event),
                            Timeout::After(Duration::from_secs(30)),
                        )
                        .await
                        .map_err(|(error, _)| {
                            NormalizerError::Config(format!("DLQ send failed: {error}"))
                        })?;
                    consumer.commit_message(&message, CommitMode::Sync)?;
                    metrics.committed_total.fetch_add(1, Ordering::Relaxed);
                    continue;
                };
                metrics.processed_total.fetch_add(1, Ordering::Relaxed);
                let event_json = normalized_event_json(&event)?;
                producer
                    .send(
                        FutureRecord::to(&config.features_topic)
                            .key(&event.entity_id)
                            .payload(&event_json),
                        Timeout::After(Duration::from_secs(30)),
                    )
                    .await
                    .map_err(|(error, _)| NormalizerError::Config(format!("features send failed: {error}")))?;

                if config.state_output_enabled && latest.accepts(&event) {
                    producer
                        .send(
                            FutureRecord::to(&config.state_topic)
                                .key(&event.entity_id)
                                .payload(&event_json),
                            Timeout::After(Duration::from_secs(30)),
                        )
                        .await
                        .map_err(|(error, _)| NormalizerError::Config(format!("state send failed: {error}")))?;
                    metrics.state_updates_total.fetch_add(1, Ordering::Relaxed);
                }

                consumer.commit_message(&message, CommitMode::Sync)?;
                metrics.committed_total.fetch_add(1, Ordering::Relaxed);
            }
            _ = &mut shutdown => {
                metrics.ready.store(false, Ordering::Relaxed);
                info!("Shutdown signal received");
                break;
            }
            _ = readiness_interval.tick() => {
                let kafka_ready = consumer
                    .fetch_metadata(None, Timeout::After(Duration::from_secs(2)))
                    .is_ok();
                metrics.ready.store(kafka_ready, Ordering::Relaxed);
                if !kafka_ready {
                    metrics.errors_total.fetch_add(1, Ordering::Relaxed);
                }
            }
        }
    }

    Ok(())
}

async fn send_dlq_event(
    producer: &FutureProducer,
    dlq_topic: &str,
    source_topic: &str,
    error_message: &str,
    raw_event: &str,
) -> Result<(), NormalizerError> {
    let event = serde_json::json!({
        "timestamp": dealiot_event_contracts::now_iso(),
        "source": "stream-normalizer",
        "intended_topic": source_topic,
        "source_topic": source_topic,
        "device_id": "unknown",
        "errors": [error_message],
        "raw_event": serde_json::from_str::<serde_json::Value>(raw_event)?,
    });
    let payload = serde_json::to_string(&event)?;
    producer
        .send(
            FutureRecord::to(dlq_topic).payload(&payload),
            Timeout::After(Duration::from_secs(30)),
        )
        .await
        .map_err(|(error, _)| NormalizerError::Config(format!("DLQ send failed: {error}")))?;
    Ok(())
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

fn kafka_consumer(config: &NormalizerConfig) -> Result<StreamConsumer, NormalizerError> {
    let mut client_config = kafka_client_config(config);
    client_config
        .set("group.id", config.consumer_group.as_str())
        .set("enable.auto.commit", "false")
        .set("enable.auto.offset.store", "false")
        .set(
            "auto.offset.reset",
            std::env::var("KAFKA_AUTO_OFFSET_RESET").unwrap_or_else(|_| "earliest".to_string()),
        );
    client_config.create().map_err(Into::into)
}

fn kafka_producer(config: &NormalizerConfig) -> Result<FutureProducer, NormalizerError> {
    kafka_client_config(config)
        .set("acks", "all")
        .set("enable.idempotence", "true")
        .set("retries", "10")
        .set("linger.ms", "50")
        .create()
        .map_err(Into::into)
}

fn kafka_client_config(config: &NormalizerConfig) -> ClientConfig {
    let mut client_config = ClientConfig::new();
    client_config.set("bootstrap.servers", config.bootstrap_servers.as_str());
    apply_security_config(&mut client_config);
    client_config
}

fn apply_security_config(client_config: &mut ClientConfig) {
    let security_protocol =
        std::env::var("KAFKA_SECURITY_PROTOCOL").unwrap_or_else(|_| "PLAINTEXT".to_string());
    client_config.set("security.protocol", security_protocol.trim());

    if security_protocol.starts_with("SASL_") {
        if let Ok(mechanism) = std::env::var("KAFKA_SASL_MECHANISM") {
            client_config.set("sasl.mechanisms", mechanism);
        }
        if let Ok(username) = std::env::var("KAFKA_SASL_USERNAME") {
            client_config.set("sasl.username", username);
        }
        if let Ok(password) = std::env::var("KAFKA_SASL_PASSWORD") {
            client_config.set("sasl.password", password);
        }
    }

    if security_protocol.contains("SSL")
        && std::env::var("KAFKA_SSL_CHECK_HOSTNAME").is_ok_and(|value| {
            matches!(
                value.trim().to_ascii_lowercase().as_str(),
                "0" | "false" | "no" | "off"
            )
        })
    {
        client_config.set("enable.ssl.certificate.verification", "false");
    }
}

fn start_health_server(bind: String, port: u16, metrics: Arc<NormalizerMetrics>) {
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
                        "# TYPE dealiot_normalizer_ready gauge\n",
                        "dealiot_normalizer_ready {}\n",
                        "# TYPE dealiot_normalizer_processed_total counter\n",
                        "dealiot_normalizer_processed_total {}\n",
                        "# TYPE dealiot_normalizer_committed_total counter\n",
                        "dealiot_normalizer_committed_total {}\n",
                        "# TYPE dealiot_normalizer_state_updates_total counter\n",
                        "dealiot_normalizer_state_updates_total {}\n",
                        "# TYPE dealiot_normalizer_errors_total counter\n",
                        "dealiot_normalizer_errors_total {}\n"
                    ),
                    u8::from(metrics.ready.load(Ordering::Relaxed)),
                    metrics.processed_total.load(Ordering::Relaxed),
                    metrics.committed_total.load(Ordering::Relaxed),
                    metrics.state_updates_total.load(Ordering::Relaxed),
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
