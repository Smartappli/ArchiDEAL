# WildFi Ingestion

DEALIoT accepts decoded WildFi gateway/tag data through the MQTT bridge. Firmware and gateway
protocols come from `https://github.com/trichl/WildFiOpenSource`; binary log decoding is handled by
`https://github.com/wildlab/WildFiDecoder`.

## Supported Ingestion Contract

Publish decoded WildFi JSON to MQTT topics under:

```text
wildfi/tags/{tag_id}/gps
wildfi/tags/{tag_id}/imu
wildfi/tags/{tag_id}/environment
wildfi/tags/{tag_id}/proximity
wildfi/gateways/{gateway_id}/tags/{tag_id}/metadata
```

The bridge subscribes to `$share/ingestors/wildfi/#` in addition to the generic device topic. GPS,
GNSS, and raw GPS topics are routed to Kafka topic `raw.gps`. IMU, environment, proximity,
metadata, movement, and decoded WildFi topics are routed to `raw.sensor`.

## GPS Payload

Use one of these timestamp fields:

- `timestamp`: ISO-8601 string,
- `utcTimestamp`: Unix timestamp in seconds or milliseconds,
- `utc_timestamp`: Unix timestamp in seconds or milliseconds.

Use `lat`/`lon` or `latitude`/`longitude` for coordinates. Example:

```json
{
  "utcTimestamp": 1704067200,
  "lat": 47.695,
  "lon": 9.132,
  "hdop": 1.4,
  "temperatureInDegCel": 18.7
}
```

## Native WildFi Binary Files

WildFi movement/proximity log files are native binary payloads. Production should not publish those
files directly as telemetry. Store the binary artifact in object storage and publish metadata, or run
the `wildlab/WildFiDecoder` image first and publish decoded JSON. The production Kubernetes overlay
includes `wildfi-decoder-config.yaml` with the decoder conversion factors and the expected MQTT
mapping.

The decoder image is built from the `WildFiDecoderMultiThreaded` component at pinned Git ref
`b4002eb9a6111de140b95e5a35c3f3bd552d51be`. A Rust runner drives the packaged
`WildFiDecoderStandalone.jar` with the documented environment variables; the WildFi binary format
itself still belongs to the upstream Java decoder. The Kubernetes production overlay includes a suspended
Job named `wildfi-decoder`; mount a PVC named `wildfi-decoder-workdir` containing the `.bin` files,
choose `WILDFI_DECODER_MODE`, then unsuspend a copied job for a decoding run.

## Configuration

Set these variables for the bridge:

```text
MQTT_TOPICS=$share/ingestors/devices/#,$share/ingestors/wildfi/#
WILDFI_DECODER_REPOSITORY=https://github.com/wildlab/WildFiDecoder
WILDFI_FIRMWARE_REPOSITORY=https://github.com/trichl/WildFiOpenSource
WILDFI_TOPIC_PREFIXES=wildfi,wild-fi
```

For Kubernetes production, update
`deploy/kubernetes/overlays/production/runtime-config.production.example.env` through a
site-specific overlay or GitOps tooling.
