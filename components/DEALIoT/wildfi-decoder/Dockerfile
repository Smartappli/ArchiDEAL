FROM rust:1.85-bookworm AS runner-builder

WORKDIR /src
COPY Cargo.toml Cargo.lock ./
COPY dealiot-event-contracts/Cargo.toml dealiot-event-contracts/Cargo.toml
COPY dealiot-event-contracts/src dealiot-event-contracts/src
COPY mqtt-kafka-bridge/Cargo.toml mqtt-kafka-bridge/Cargo.toml
COPY mqtt-kafka-bridge/src mqtt-kafka-bridge/src
COPY stream-normalizer/Cargo.toml stream-normalizer/Cargo.toml
COPY stream-normalizer/src stream-normalizer/src
COPY wildfi-decoder-runner/Cargo.toml wildfi-decoder-runner/Cargo.toml
COPY wildfi-decoder-runner/src wildfi-decoder-runner/src
RUN cargo build --release --locked -p dealiot-wildfi-decoder-runner

FROM eclipse-temurin:21-jre-jammy AS source

ARG WILDFI_DECODER_GIT_REF=b4002eb9a6111de140b95e5a35c3f3bd552d51be

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git init WildFiDecoder \
    && cd WildFiDecoder \
    && git remote add origin https://github.com/wildlab/WildFiDecoder.git \
    && git fetch --depth=1 origin "${WILDFI_DECODER_GIT_REF}" \
    && git checkout --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "${WILDFI_DECODER_GIT_REF}"

FROM eclipse-temurin:21-jre-jammy

ENV WILDFI_DECODER_HOME=/opt/wildfi-decoder \
    WILDFI_DECODER_WORKDIR=/work \
    WILDFI_DECODER_MODE=2 \
    WILDFI_DECODER_BURST_FORM=0 \
    WILDFI_DECODER_FILE_INDEX=0 \
    WILDFI_DECODER_TAG_SELECTION=0 \
    WILDFI_IMU_FREQUENCY=25

RUN groupadd --system wildfi \
    && useradd --system --gid wildfi --home-dir /nonexistent --shell /usr/sbin/nologin wildfi \
    && mkdir -p "${WILDFI_DECODER_HOME}" "${WILDFI_DECODER_WORKDIR}" \
    && chown -R wildfi:wildfi "${WILDFI_DECODER_HOME}" "${WILDFI_DECODER_WORKDIR}"

WORKDIR ${WILDFI_DECODER_HOME}

COPY --from=source --chown=wildfi:wildfi \
    /src/WildFiDecoder/WildFiDecoderMultiThreaded/WildFiDecoderStandalone.jar \
    /src/WildFiDecoder/WildFiDecoderMultiThreaded/WildFiDecoderConfig.txt \
    /opt/wildfi-decoder/
COPY --from=runner-builder --chown=wildfi:wildfi --chmod=0555 \
    /src/target/release/run-wildfi-decoder \
    /usr/local/bin/run-wildfi-decoder

USER wildfi
WORKDIR /work

ENTRYPOINT ["run-wildfi-decoder"]
