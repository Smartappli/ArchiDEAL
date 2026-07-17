#!/usr/bin/env bash
set -euo pipefail

decoder_home="${WILDFI_DECODER_HOME:-/opt/wildfi-decoder}"
workdir="${WILDFI_DECODER_WORKDIR:-/work}"
mode="${WILDFI_DECODER_MODE:-2}"

run_decoder() {
  env -u JAVA_TOOL_OPTIONS -u JDK_JAVA_OPTIONS \
    java -Djava.io.tmpdir="${TMPDIR:-/tmp}" -jar "${decoder_home}/WildFiDecoderStandalone.jar"
}

cd "$workdir"

if [[ -n "${WILDFI_DECODER_RAW_INPUT:-}" ]]; then
  printf '%b' "$WILDFI_DECODER_RAW_INPUT" | run_decoder
  exit 0
fi

case "$mode" in
  1 | 2)
    printf '%s\n%s\n%s\n%s\n%s\n\n99\n' \
      "$mode" \
      "${WILDFI_DECODER_BURST_FORM:-0}" \
      "${WILDFI_DECODER_FILE_INDEX:-0}" \
      "${WILDFI_DECODER_TAG_SELECTION:-0}" \
      "${WILDFI_IMU_FREQUENCY:-25}" \
      | run_decoder
    ;;
  3 | 4 | 5 | 6 | 7 | 8)
    printf '%s\n\n99\n' "$mode" | run_decoder
    ;;
  *)
    echo "Unsupported WILDFI_DECODER_MODE=$mode. Use 1, 2, 3, 4, 5, 6, 7, 8 or WILDFI_DECODER_RAW_INPUT." >&2
    exit 64
    ;;
esac
