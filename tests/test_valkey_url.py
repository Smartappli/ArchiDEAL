from __future__ import annotations

import base64
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "deploy/kubernetes/validate-valkey-url.py"


class ValkeyURLValidatorTests(unittest.TestCase):
    def validate(
        self,
        value: str,
        *,
        expected_host: str = "valkey.prod.internal.corp",
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                "--expected-host",
                expected_host,
            ],
            cwd=ROOT,
            input=base64.b64encode(value.encode()),
            capture_output=True,
            check=False,
        )

    def test_accepts_rediss_on_approved_host_and_tls_port(self) -> None:
        result = self.validate(
            "rediss://session-user:secret@valkey.prod.internal.corp:6380/1"
        )

        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn(b"contract validated", result.stdout)

    def test_rejects_plaintext_redis_without_disclosing_secret(self) -> None:
        secret_url = "redis://session-user:do-not-print@valkey.prod.internal.corp:6380/1"
        result = self.validate(secret_url)

        self.assertEqual(result.returncode, 2)
        self.assertIn(b"must use rediss://", result.stderr)
        self.assertNotIn(b"do-not-print", result.stderr)

    def test_rejects_unapproved_host(self) -> None:
        result = self.validate("rediss://valkey.attacker.example:6380/1")

        self.assertEqual(result.returncode, 2)
        self.assertIn(b"does not match", result.stderr)

    def test_rejects_non_tls_contract_port(self) -> None:
        result = self.validate("rediss://valkey.prod.internal.corp:6379/1")

        self.assertEqual(result.returncode, 2)
        self.assertIn(b"TLS port 6380", result.stderr)

    def test_rejects_missing_authentication(self) -> None:
        result = self.validate("rediss://valkey.prod.internal.corp:6380/1")

        self.assertEqual(result.returncode, 2)
        self.assertIn(b"ACL password", result.stderr)

    def test_rejects_options_that_can_disable_certificate_verification(self) -> None:
        secret_url = (
            "rediss://session-user:do-not-print@valkey.prod.internal.corp:6380/1"
            "?ssl_cert_reqs=none"
        )
        result = self.validate(secret_url)

        self.assertEqual(result.returncode, 2)
        self.assertIn(b"query options are forbidden", result.stderr)
        self.assertNotIn(b"do-not-print", result.stderr)


if __name__ == "__main__":
    unittest.main()
