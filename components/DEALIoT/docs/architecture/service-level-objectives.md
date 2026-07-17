# Service Level Objectives

These initial objectives apply to production over a rolling 30-day window. Every alert has an
operational owner and consumes the associated error budget.

| Service indicator | Objective | Alert owner |
|---|---:|---|
| MQTT event accepted and durably written to Kafka | 99.9% | ingestion on-call |
| MQTT-to-Kafka p95 latency | below 5 seconds | ingestion on-call |
| Invalid-event DLQ ratio | below 0.5% | data contract owner |
| Stateful processing availability | 99.9% | streaming on-call |
| Kafka consumer lag age p95 | below 60 seconds | streaming on-call |
| Successful Flink checkpoints | 99.5% | streaming on-call |
| Airflow production DAG success | 99% | data operations |
| Object storage request availability | 99.9% | platform on-call |

Fast burn alerts trigger when 10% of a monthly error budget is consumed in one hour. Slow burn
alerts trigger when 25% is consumed in one day. Release decisions must include the current error
budget and any open critical alerts.

Metrics that cannot yet be measured are rollout blockers, not silently exempt objectives.
