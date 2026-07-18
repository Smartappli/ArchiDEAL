# syntax=docker/dockerfile:1.7

FROM rust:1.89-bookworm@sha256:948f9b08a66e7fe01b03a98ef1c7568292e07ec2e4fe90d88c07bb14563c84ff AS builder

WORKDIR /src

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates cmake libssl-dev pkg-config \
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

RUN set -eux; \
    runtime_root=/runtime-root; \
    binary=/src/target/release/dealiot-mqtt-kafka-bridge; \
    mkdir -p \
      "$runtime_root/etc/ssl/certs" \
      "$runtime_root/usr/lib/ssl" \
      "$runtime_root/usr/local/bin" \
      "$runtime_root/var/lib/dpkg"; \
    cp "$binary" "$runtime_root/usr/local/bin/dealiot-mqtt-kafka-bridge"; \
    cp /etc/os-release /etc/debian_version /etc/nsswitch.conf "$runtime_root/etc/"; \
    cp /etc/ssl/certs/ca-certificates.crt "$runtime_root/etc/ssl/certs/"; \
    ln -s /etc/ssl/certs/ca-certificates.crt "$runtime_root/usr/lib/ssl/cert.pem"; \
    ldd "$binary" \
      | awk '$2 == "=>" && $3 ~ /^\// { print $3 } $1 ~ /^\// { print $1 }' \
      | sort -u \
      > /tmp/runtime-libraries; \
    while IFS= read -r library; do cp --parents "$library" "$runtime_root"; done \
      < /tmp/runtime-libraries; \
    for library in libnss_dns.so.2 libnss_files.so.2 libresolv.so.2; do \
      cp --parents "/lib/x86_64-linux-gnu/$library" "$runtime_root"; \
    done; \
    dpkg-query -s ca-certificates libc6 libgcc-s1 libssl3 \
      > "$runtime_root/var/lib/dpkg/status"; \
    test ! -e "$runtime_root/usr/bin/perl"; \
    test ! -e "$runtime_root/usr/bin/wget"; \
    chmod 0555 "$runtime_root/usr/local/bin/dealiot-mqtt-kafka-bridge"

# scratch is Docker's immutable, empty built-in base. The copied dpkg inventory keeps native
# runtime libraries visible to scanners without carrying unrelated Debian utilities.
FROM scratch

COPY --from=builder --chown=0:0 /runtime-root/ /

USER 10001:10001
ENV RUST_LOG="info"
ENV SSL_CERT_FILE="/etc/ssl/certs/ca-certificates.crt"
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
  CMD ["/usr/local/bin/dealiot-mqtt-kafka-bridge", "--healthcheck"]
CMD ["/usr/local/bin/dealiot-mqtt-kafka-bridge"]
