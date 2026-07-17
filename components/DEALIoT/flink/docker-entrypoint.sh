#!/usr/bin/env sh
set -eu

read_secret() {
  secret_path="$1"
  if [ -r "$secret_path" ]; then
    tr -d '\r\n' <"$secret_path"
  fi
}

ACCESS_KEY="${AWS_ACCESS_KEY_ID:-${SEAWEEDFS_S3_ACCESS_KEY:-}}"
SECRET_KEY="${AWS_SECRET_ACCESS_KEY:-${SEAWEEDFS_S3_SECRET_KEY:-}}"

if [ -r /run/secrets/seaweedfs_s3_access_key ]; then
  ACCESS_KEY="$(read_secret /run/secrets/seaweedfs_s3_access_key)"
fi

if [ -r /run/secrets/seaweedfs_s3_secret_key ]; then
  SECRET_KEY="$(read_secret /run/secrets/seaweedfs_s3_secret_key)"
fi

if [ -n "$ACCESS_KEY" ]; then
  export AWS_ACCESS_KEY_ID="$ACCESS_KEY"
  export SEAWEEDFS_S3_ACCESS_KEY="$ACCESS_KEY"
fi

if [ -n "$SECRET_KEY" ]; then
  export AWS_SECRET_ACCESS_KEY="$SECRET_KEY"
  export SEAWEEDFS_S3_SECRET_KEY="$SECRET_KEY"
fi

export AWS_EC2_METADATA_DISABLED="${AWS_EC2_METADATA_DISABLED:-true}"

if [ -n "$ACCESS_KEY" ] && [ -n "$SECRET_KEY" ] && [ -n "${FLINK_PROPERTIES:-}" ]; then
  FLINK_PROPERTIES="$(
    printf '%s\n' "$FLINK_PROPERTIES" | awk '
      /^[[:space:]]*s3\.access-key[[:space:]]*:/ { next }
      /^[[:space:]]*s3\.secret-key[[:space:]]*:/ { next }
      { print }
    '
  )
$(printf 's3.access-key: %s\ns3.secret-key: %s' "$ACCESS_KEY" "$SECRET_KEY")"
  export FLINK_PROPERTIES
fi

exec /docker-entrypoint.sh "$@"
