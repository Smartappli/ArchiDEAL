# syntax=docker/dockerfile:1.7

FROM rust:1.89-bookworm@sha256:948f9b08a66e7fe01b03a98ef1c7568292e07ec2e4fe90d88c07bb14563c84ff AS builder

WORKDIR /src

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates cmake g++ libcurl4-openssl-dev musl-tools perl pkg-config \
 && rm -rf /var/lib/apt/lists/*

RUN rustup target add x86_64-unknown-linux-musl

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

ENV CARGO_BUILD_TARGET=x86_64-unknown-linux-musl \
    CFLAGS_x86_64_unknown_linux_musl=-I/usr/include/x86_64-linux-gnu \
    CXX_x86_64_unknown_linux_musl=g++

RUN cargo build --release --locked -p dealiot-mqtt-kafka-bridge

RUN set -eux; \
    runtime_root=/runtime-root; \
    binary=/src/target/x86_64-unknown-linux-musl/release/dealiot-mqtt-kafka-bridge; \
    mkdir -p \
      "$runtime_root/etc/ssl/certs" \
      "$runtime_root/usr/local/bin"; \
    cp "$binary" "$runtime_root/usr/local/bin/dealiot-mqtt-kafka-bridge"; \
    cp /etc/ssl/certs/ca-certificates.crt "$runtime_root/etc/ssl/certs/"; \
    test ! -e "$runtime_root/usr/bin/perl"; \
    test ! -e "$runtime_root/usr/bin/wget"; \
    chmod 0555 "$runtime_root/usr/local/bin/dealiot-mqtt-kafka-bridge"

# scratch is Docker's immutable, empty built-in base. The bridge is a statically linked musl binary;
# the runtime contains only that binary and the CA trust store required for TLS.
FROM scratch

COPY --from=builder --chown=0:0 /runtime-root/ /

USER 10001:10001
ENV RUST_LOG="info"
ENV SSL_CERT_FILE="/etc/ssl/certs/ca-certificates.crt"
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
  CMD ["/usr/local/bin/dealiot-mqtt-kafka-bridge", "--healthcheck"]
CMD ["/usr/local/bin/dealiot-mqtt-kafka-bridge"]
