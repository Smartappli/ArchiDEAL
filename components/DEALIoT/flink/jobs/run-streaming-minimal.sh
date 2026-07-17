#!/usr/bin/env sh
set -eu

/opt/flink/bin/flink run -d \
  --jobmanager flink-jobmanager:8081 \
  --python /opt/flink/usrlib/streaming_minimal.py \
  --pyclientexec /opt/flink/venv/bin/python \
  --pyexec /opt/flink/venv/bin/python
