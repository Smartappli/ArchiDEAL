"""Consume DEALIoT Kafka `raw.sensor` events into the sensor layer."""

from sensor_data.ingestion import ingest_dealiot_sensor_event

from dealdata_common.kafka import build_dealiot_kafka_command

Command = build_dealiot_kafka_command(
    service_key="sensor",
    event_label="sensor",
    model_path="sensor_data.WildFiDecodedSensorEvent",
    ingest_event=ingest_dealiot_sensor_event,
)
