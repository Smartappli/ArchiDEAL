"""Consume DEALIoT Kafka `raw.gps` events into the GPS layer."""

from gps_data.ingestion import ingest_dealiot_gps_event

from dealdata_common.kafka import build_dealiot_kafka_command

Command = build_dealiot_kafka_command(
    service_key="gps",
    event_label="GPS",
    model_path="gps_data.GPSFix",
    ingest_event=ingest_dealiot_gps_event,
)
