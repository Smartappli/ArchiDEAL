# syntax=docker/dockerfile:1.7

FROM rust:1.85-bookworm AS builder

WORKDIR /src

RUN apt-get update \
 && apt-get install -y --no-install-recommends cmake pkg-config libssl-dev libsasl2-dev ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY --chmod=0444 Cargo.toml /src/Cargo.toml
COPY --chmod=0444 Cargo.lock /src/Cargo.lock
COPY --chmod=0444 dealiot-event-contracts/Cargo.toml /src/dealiot-event-contracts/Cargo.toml
COPY --chmod=0444 dealiot-event-contracts/src /src/dealiot-event-contracts/src
COPY --chmod=0444 mqtt-kafka-bridge/Cargo.toml /src/mqtt-kafka-bridge/Cargo.toml
COPY --chmod=0444 mqtt-kafka-bridge/src /src/mqtt-kafka-bridge/src
COPY --chmod=0444 stream-normalizer/Cargo.toml /src/stream-normalizer/Cargo.toml
COPY --chmod=0444 stream-normalizer/src /src/stream-normalizer/src
COPY --chmod=0444 wildfi-decoder-runner/Cargo.toml /src/wildfi-decoder-runner/Cargo.toml
COPY --chmod=0444 wildfi-decoder-runner/src /src/wildfi-decoder-runner/src

RUN cargo build --release --locked -p dealiot-mqtt-kafka-bridge

FROM debian:bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates libsasl2-2 wget \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --create-home --shell /usr/sbin/nologin appuser

COPY --from=builder --chown=root:root --chmod=0555 \
  /src/target/release/dealiot-mqtt-kafka-bridge \
  /usr/local/bin/dealiot-mqtt-kafka-bridge

USER appuser
ENV RUST_LOG="info"
CMD ["dealiot-mqtt-kafka-bridge"]
