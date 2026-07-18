from __future__ import annotations

import unittest

from dealdata_common.kafka_preflight import (
    DEFAULT_REQUIRED_TOPICS,
    validate_topic_configs,
    validate_topic_metadata,
)


def metadata(*, partitions: int = 3, replicas: int = 3, isr: int = 2):
    return [
        {
            "topic": topic,
            "error_code": 0,
            "partitions": [
                {
                    "partition": partition,
                    "replicas": list(range(replicas)),
                    "isr": list(range(isr)),
                }
                for partition in range(partitions)
            ],
        }
        for topic in DEFAULT_REQUIRED_TOPICS
    ]


class KafkaPreflightTests(unittest.TestCase):
    def test_accepts_healthy_three_broker_topic_contract(self) -> None:
        self.assertEqual(
            validate_topic_metadata(
                metadata(),
                DEFAULT_REQUIRED_TOPICS,
                minimum_partitions=3,
                minimum_replication_factor=3,
                minimum_in_sync_replicas=2,
            ),
            [],
        )

    def test_reports_missing_under_replicated_and_under_isr_topics(self) -> None:
        descriptions = metadata(replicas=2, isr=1)
        descriptions.pop()
        errors = validate_topic_metadata(
            descriptions,
            DEFAULT_REQUIRED_TOPICS,
            minimum_partitions=3,
            minimum_replication_factor=3,
            minimum_in_sync_replicas=2,
        )
        self.assertTrue(any("topic is missing" in error for error in errors))
        self.assertTrue(any("replication_factor=2" in error for error in errors))
        self.assertTrue(any("in_sync_replicas=1" in error for error in errors))

    def test_reports_too_few_partitions_and_kafka_errors(self) -> None:
        descriptions = metadata(partitions=2)
        descriptions[0]["error_code"] = 3
        errors = validate_topic_metadata(
            descriptions,
            DEFAULT_REQUIRED_TOPICS,
            minimum_partitions=3,
            minimum_replication_factor=3,
            minimum_in_sync_replicas=2,
        )
        self.assertTrue(any("error_code=3" in error for error in errors))
        self.assertTrue(any("partitions=2" in error for error in errors))

    def test_requires_durable_topic_configuration(self) -> None:
        configurations = {
            "topic": {
                topic: {
                    "min.insync.replicas": {"value": "2"},
                    "unclean.leader.election.enable": {"value": "false"},
                }
                for topic in DEFAULT_REQUIRED_TOPICS
            },
        }
        self.assertEqual(
            validate_topic_configs(
                configurations,
                DEFAULT_REQUIRED_TOPICS,
                minimum_in_sync_replicas=2,
            ),
            [],
        )

        configurations["topic"][DEFAULT_REQUIRED_TOPICS[0]][
            "min.insync.replicas"
        ] = {"value": "1"}
        configurations["topic"][DEFAULT_REQUIRED_TOPICS[1]][
            "unclean.leader.election.enable"
        ] = {"value": "true"}
        errors = validate_topic_configs(
            configurations,
            DEFAULT_REQUIRED_TOPICS,
            minimum_in_sync_replicas=2,
        )
        self.assertTrue(any("min.insync.replicas=1" in error for error in errors))
        self.assertTrue(any("unclean.leader" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
