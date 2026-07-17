from __future__ import annotations

import argparse
import json
import mimetypes
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import boto3
from kafka import KafkaProducer

from dealiot_contracts import (
    DLQ_TOPIC,
    RAW_IMAGE2D_META_TOPIC,
    RAW_IMAGE3D_META_TOPIC,
    RAW_VIDEO2D_META_TOPIC,
    RAW_VIDEO3D_META_TOPIC,
    build_dlq_event,
    now_iso,
    validate_event,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

TOPIC_BY_MEDIA_KIND = {
    "image2d": RAW_IMAGE2D_META_TOPIC,
    "image3d": RAW_IMAGE3D_META_TOPIC,
    "video2d": RAW_VIDEO2D_META_TOPIC,
    "video3d": RAW_VIDEO3D_META_TOPIC,
}
TRUTHY_VALUES = {"1", "true", "yes", "on"}


def bool_env(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in TRUTHY_VALUES


def kafka_security_config() -> dict[str, bool | str]:
    security_protocol = os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT").strip()
    config: dict[str, bool | str] = {"security_protocol": security_protocol}

    if security_protocol.startswith("SASL_"):
        username = os.getenv("KAFKA_SASL_USERNAME")
        password = os.getenv("KAFKA_SASL_PASSWORD")
        if not username or not password:
            raise ValueError(
                "KAFKA_SASL_USERNAME and KAFKA_SASL_PASSWORD must both be set when "
                "Kafka SASL is enabled.",
            )
        config["sasl_mechanism"] = os.getenv("KAFKA_SASL_MECHANISM", "SCRAM-SHA-512")
        config["sasl_plain_username"] = username
        config["sasl_plain_password"] = password

    if "SSL" in security_protocol:
        ssl_cafile = os.getenv("KAFKA_SSL_CAFILE")
        ssl_certfile = os.getenv("KAFKA_SSL_CERTFILE")
        ssl_keyfile = os.getenv("KAFKA_SSL_KEYFILE")
        if ssl_cafile:
            config["ssl_cafile"] = ssl_cafile
        if ssl_certfile:
            config["ssl_certfile"] = ssl_certfile
        if ssl_keyfile:
            config["ssl_keyfile"] = ssl_keyfile
        config["ssl_check_hostname"] = bool_env("KAFKA_SSL_CHECK_HOSTNAME", default=True)

    return {key: value for key, value in config.items() if value not in (None, "")}


def parse_iso8601(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def guess_format(object_key: str) -> str:
    suffix = Path(object_key).suffix.lower().lstrip(".")
    return suffix or "bin"


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )


def get_kafka_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=os.environ["KAFKA_BOOTSTRAP_SERVERS"].split(","),
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
        acks="all",
        retries=10,
        linger_ms=50,
        compression_type="lz4",
        **kafka_security_config(),
    )


def iter_objects_between(
    bucket: str,
    prefix: str,
    window_start: datetime,
    window_end: datetime,
) -> Iterator[dict]:
    s3 = get_s3_client()
    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            last_modified = item["LastModified"].astimezone(UTC)
            if window_start <= last_modified < window_end:
                yield {
                    "bucket": bucket,
                    "object_key": item["Key"],
                    "size_bytes": item["Size"],
                    "timestamp": last_modified.isoformat(),
                    "object_uri": f"s3://{bucket}/{item['Key']}",
                }


def build_record(obj: dict, media_kind: str) -> dict:
    content_type, _ = mimetypes.guess_type(obj["object_key"])
    record = {
        "device_id": "backfill",
        "timestamp": obj["timestamp"],
        "ingested_at": now_iso(),
        "bucket": obj["bucket"],
        "object_key": obj["object_key"],
        "object_uri": obj["object_uri"],
        "format": guess_format(obj["object_key"]),
        "content_type": content_type or "application/octet-stream",
        "size_bytes": obj["size_bytes"],
        "tags": {
            "source": "airflow-backfill",
            "media_kind": media_kind,
        },
    }

    media_defaults = {
        "image2d": {"camera_id": "unknown"},
        "image3d": {"sensor_id": "unknown", "capture_type": "unknown"},
        "video2d": {"camera_id": "unknown"},
        "video3d": {"rig_id": "unknown", "representation": "unknown"},
    }
    record.update(media_defaults.get(media_kind, {}))

    return record


def resolve_window(args: argparse.Namespace) -> tuple[datetime, datetime]:
    if args.window_start or args.window_end:
        if not (args.window_start and args.window_end):
            raise ValueError(
                "Both --window-start and --window-end must be set together.",
            )
        window_start = parse_iso8601(args.window_start)
        window_end = parse_iso8601(args.window_end)
        if window_start >= window_end:
            raise ValueError("--window-start must be earlier than --window-end.")
        return window_start, window_end

    if args.since_minutes is None:
        raise ValueError("Use either --window-start/--window-end or --since-minutes.")
    if args.since_minutes <= 0:
        raise ValueError("--since-minutes must be a positive integer.")

    window_end = datetime.now(UTC)
    window_start = window_end - timedelta(minutes=args.since_minutes)
    return window_start, window_end


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--prefix", default="")
    parser.add_argument("--since-minutes", type=int)
    parser.add_argument("--window-start")
    parser.add_argument("--window-end")
    parser.add_argument("--media-kind", required=True, choices=sorted(TOPIC_BY_MEDIA_KIND))

    args = parser.parse_args()
    window_start, window_end = resolve_window(args)
    kafka_topic = TOPIC_BY_MEDIA_KIND[args.media_kind]
    producer = get_kafka_producer()

    sent = 0
    invalid = 0
    for obj in iter_objects_between(
        bucket=args.bucket,
        prefix=args.prefix,
        window_start=window_start,
        window_end=window_end,
    ):
        record = build_record(obj, args.media_kind)
        key = obj["object_key"].encode("utf-8")
        errors = validate_event(kafka_topic, record)
        if errors:
            raw_event = {
                **record,
                "source_topic": f"s3://{obj['bucket']}/{obj['object_key']}",
            }
            producer.send(
                DLQ_TOPIC,
                key=key,
                value=build_dlq_event(
                    source="airflow-backfill",
                    intended_topic=kafka_topic,
                    errors=errors,
                    raw_event=raw_event,
                ),
            )
            invalid += 1
        else:
            producer.send(kafka_topic, key=key, value=record)
            sent += 1

    producer.flush(timeout=30)
    print(
        json.dumps(
            {
                "bucket": args.bucket,
                "media_kind": args.media_kind,
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "topic": kafka_topic,
                "records_sent": sent,
                "records_invalid": invalid,
            }
        )
    )


if __name__ == "__main__":
    main()
