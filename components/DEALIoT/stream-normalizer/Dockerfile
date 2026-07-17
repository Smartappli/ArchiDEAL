FROM rust:1.85-bookworm AS builder

WORKDIR /src

RUN apt-get update \
    && apt-get install -y --no-install-recommends cmake pkg-config libssl-dev libsasl2-dev libcurl4-openssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY Cargo.toml Cargo.lock ./
COPY dealiot-event-contracts/Cargo.toml dealiot-event-contracts/Cargo.toml
COPY dealiot-event-contracts/src dealiot-event-contracts/src
COPY mqtt-kafka-bridge/Cargo.toml mqtt-kafka-bridge/Cargo.toml
COPY mqtt-kafka-bridge/src mqtt-kafka-bridge/src
COPY stream-normalizer/Cargo.toml stream-normalizer/Cargo.toml
COPY stream-normalizer/src stream-normalizer/src
COPY wildfi-decoder-runner/Cargo.toml wildfi-decoder-runner/Cargo.toml
COPY wildfi-decoder-runner/src wildfi-decoder-runner/src

RUN cargo build --release --locked -p dealiot-stream-normalizer

FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libsasl2-2 wget \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system appuser \
    && useradd --system --gid appuser --home-dir /nonexistent --shell /usr/sbin/nologin appuser

COPY --from=builder --chown=root:root --chmod=0555 \
    /src/target/release/dealiot-stream-normalizer \
    /usr/local/bin/dealiot-stream-normalizer

USER appuser

CMD ["dealiot-stream-normalizer"]
