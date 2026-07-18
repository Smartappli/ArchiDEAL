from __future__ import annotations

import os
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent.parent
DEPLOYER = ROOT / "deploy/kubernetes/deploy-production.sh"
ROLLBACK = ROOT / "deploy/kubernetes/rollback-production.sh"


class ProductionRollbackTests(unittest.TestCase):
    def test_failure_trap_fences_ingress_and_preserves_original_status(self) -> None:
        script = DEPLOYER.read_text(encoding="utf-8")

        self.assertIn("trap on_exit EXIT", script)
        self.assertIn("local original_status=$?", script)
        self.assertIn('exit "$original_status"', script)
        first_mutation = script.index('mutation_started="true"')
        namespace_apply = script.index('apply_cluster_file "$rendered/base/namespace.yaml"')
        self.assertLess(first_mutation, namespace_apply)
        self.assertIn('delete ingress/archideal', script)
        self.assertIn('--for=delete ingress/archideal', script)
        self.assertIn("annotate_promotion_state failed", script)
        self.assertIn("production-rollback", script)
        self.assertIn('"$rollback_root/source"', script)
        self.assertIn("APPROVE_SCHEMA_COMPATIBLE_ROLLBACK=1", script)

    def test_active_and_promoted_releases_are_proven_coherent(self) -> None:
        script = DEPLOYER.read_text(encoding="utf-8")
        coherence_calls = [
            index
            for index in range(len(script))
            if script.startswith("validate-release-coherence.py", index)
        ]
        self.assertEqual(len(coherence_calls), 2)
        first_mutation = script.index('mutation_started="true"')
        public_smoke = script.index("--exercise-api-ingest")
        promotion_complete = script.index('promotion_succeeded="true"')
        self.assertLess(coherence_calls[0], first_mutation)
        self.assertLess(public_smoke, coherence_calls[1])
        self.assertLess(coherence_calls[1], promotion_complete)
        self.assertIn('"archideal.io/promotion-state=succeeded"', script)
        self.assertIn('"archideal.io/previous-release=$previous_release"', script)

    def test_rollback_wrapper_reuses_full_signed_deployer_without_schema_reverse(self) -> None:
        self.assertTrue(os.access(ROLLBACK, os.X_OK))
        result = subprocess.run(
            ["bash", "-n", str(ROLLBACK)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        script = ROLLBACK.read_text(encoding="utf-8")
        for argument in (
            "--release-manifest",
            "--release-bundle",
            "--release-evidence-dir",
            "--approve-schema-compatible",
        ):
            self.assertIn(argument, script)
        self.assertIn('recorded_previous" != "$target_release', script)
        self.assertIn('exec "$script_dir/deploy-production.sh"', script)
        self.assertIn("--approve-live-upgrade", script)
        self.assertNotIn("migrate --fake", script)
        self.assertNotIn("migrate zero", script)
        self.assertNotIn("pg_restore", script)

        makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        target = makefile.split("production-rollback:", 1)[1]
        self.assertIn("deploy/kubernetes/rollback-production.sh", target)
        self.assertIn("ROLLBACK_RELEASE_MANIFEST", target)
        self.assertIn("ROLLBACK_RELEASE_BUNDLE", target)
        self.assertIn("ROLLBACK_RELEASE_EVIDENCE_DIR", target)
        self.assertIn("APPROVE_SCHEMA_COMPATIBLE_ROLLBACK", target)


if __name__ == "__main__":
    unittest.main()
