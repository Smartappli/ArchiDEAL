# syntax=docker/dockerfile:1.7

FROM rust:1.85-bookworm@sha256:e51d0265072d2d9d5d320f6a44dde6b9ef13653b035098febd68cce8fa7c0bc4 AS builder

WORKDIR /src

RUN apt-get update \
 && apt-get install -y --no-install-recommends cmake pkg-config libssl-dev libsasl2-dev libcurl4-openssl-dev ca-certificates \
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

FROM debian:bookworm-slim@sha256:7b140f374b289a7c2befc338f42ebe6441b7ea838a042bbd5acbfca6ec875818

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates libsasl2-2 wget \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --gid 10001 appuser \
 && useradd --uid 10001 --gid appuser --create-home --shell /usr/sbin/nologin appuser

COPY --from=builder --chown=root:root --chmod=0555 \
  /src/target/release/dealiot-mqtt-kafka-bridge \
  /usr/local/bin/dealiot-mqtt-kafka-bridge

USER 10001:10001
ENV RUST_LOG="info"
CMD ["dealiot-mqtt-kafka-bridge"]
