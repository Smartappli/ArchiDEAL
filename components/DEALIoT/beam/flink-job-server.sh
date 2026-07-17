#!/bin/sh
set -eu

java -cp "jars/*" org.apache.beam.runners.flink.FlinkJobServerDriver "$@" &
wait
