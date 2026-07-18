import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")


def service_block(name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:|^secrets:|\Z)",
        COMPOSE,
    )
    if match is None:
        raise AssertionError(f"Missing production service: {name}")
    return match.group("body")


class ProductionComposeSecurityTests(unittest.TestCase):
    def test_all_database_clients_verify_postgres_hostname_and_mount_ca_read_only(self) -> None:
        for service in ("core", "gps", "sensor", "gps-dealiot-consumer", "sensor-dealiot-consumer"):
            with self.subTest(service=service):
                block = service_block(service)
                self.assertIn("DATABASE_SSLMODE: verify-full", block)
                self.assertIn(
                    "DATABASE_SSLROOTCERT: /run/secrets/dealdata-postgres-ca.crt",
                    block,
                )
                self.assertIn("source: dealdata-postgres-ca", block)
                self.assertIn("target: dealdata-postgres-ca.crt", block)
                self.assertIn("mode: 0444", block)

    def test_kafka_consumers_require_sasl_ssl_credentials_and_verified_ca(self) -> None:
        for service in ("gps-dealiot-consumer", "sensor-dealiot-consumer"):
            with self.subTest(service=service):
                block = service_block(service)
                self.assertIn("DEALDATA_KAFKA_SECURITY_PROTOCOL: SASL_SSL", block)
                self.assertRegex(
                    block,
                    r"DEALDATA_KAFKA_SASL_USERNAME: \$\{[^}]+:\?set [^}]+\}",
                )
                self.assertRegex(
                    block,
                    r"DEALDATA_KAFKA_SASL_PASSWORD: \$\{[^}]+:\?set [^}]+\}",
                )
                self.assertIn(
                    "DEALDATA_KAFKA_SSL_CAFILE: /run/secrets/dealdata-kafka-ca.crt",
                    block,
                )
                self.assertIn('DEALDATA_KAFKA_SSL_CHECK_HOSTNAME: "true"', block)
                self.assertIn("source: dealdata-kafka-ca", block)
                self.assertIn("target: dealdata-kafka-ca.crt", block)

    def test_ca_sources_are_external_required_compose_secrets(self) -> None:
        self.assertIn(
            "file: ${DATABASE_SSLROOTCERT_SOURCE:?set DATABASE_SSLROOTCERT_SOURCE}",
            COMPOSE,
        )
        self.assertIn(
            "file: ${DEALDATA_KAFKA_SSL_CAFILE_SOURCE:?set "
            "DEALDATA_KAFKA_SSL_CAFILE_SOURCE}",
            COMPOSE,
        )


if __name__ == "__main__":
    unittest.main()
