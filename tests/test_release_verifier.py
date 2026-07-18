from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "deploy/kubernetes/verify-release.py"
POLICY = ROOT / "deploy/kubernetes/supply-chain-policy.yaml"
EXAMPLE_VALUES = ROOT / "deploy/kubernetes/values.example.yaml"
RELEASE_WORKFLOW = ROOT / ".github/workflows/release-images.yml"
UPSTREAM_CONFIG = ROOT / "deploy/kubernetes/upstream-images.json"
UPSTREAM_CONFIG_VALIDATOR = ROOT / "scripts/release-upstream-config.py"


class ReleaseVerifierTests(unittest.TestCase):
    def test_every_main_head_produces_signed_release_evidence(self) -> None:
        workflow = yaml.load(
            RELEASE_WORKFLOW.read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )
        triggers = workflow["on"]
        self.assertEqual(triggers["push"]["branches"], ["main"])
        self.assertNotIn("paths", triggers["push"])
        self.assertIn("workflow_dispatch", triggers)

    def test_release_matrix_matches_ten_image_policy(self) -> None:
        policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))["images"]
        workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
        upstream_config = json.loads(UPSTREAM_CONFIG.read_text(encoding="utf-8"))
        jobs = workflow["jobs"]
        first_party = {
            item["values_key"]: item
            for item in jobs["build-scan-sign"]["strategy"]["matrix"]["include"]
        }
        upstream = {
            item["values_key"]: item
            for item in upstream_config["images"]
        }
        self.assertEqual(
            set(first_party),
            {key for key, image in policy.items() if image["kind"] == "first-party"},
        )
        self.assertEqual(
            set(upstream),
            {key for key, image in policy.items() if image["kind"] == "upstream"},
        )
        for values_key, matrix in first_party.items():
            self.assertEqual(matrix["name"], policy[values_key]["component"])
            self.assertEqual(matrix["context"], policy[values_key]["context"])
            self.assertEqual(matrix["dockerfile"], policy[values_key]["dockerfile"])
        for values_key, matrix in upstream.items():
            self.assertEqual(matrix["name"], policy[values_key]["component"])
            self.assertEqual(
                matrix["expected_repository"], policy[values_key]["repository"]
            )
            self.assertEqual(
                matrix["source_repository"], policy[values_key]["sourceRepository"]
            )
            self.assertEqual(
                matrix["build_repository"], policy[values_key]["buildRepository"]
            )
            self.assertEqual(
                matrix["source_release_prefix"],
                policy[values_key]["sourceReleasePrefix"],
            )
            self.assertEqual(
                matrix["minimum_version"], policy[values_key]["minimumVersion"]
            )
            self.assertEqual(
                matrix["image_tag_suffix"], policy[values_key]["imageTagSuffix"]
            )
            self.assertEqual(
                matrix["runtime_contract"], policy[values_key]["runtimeContract"]
            )
        self.assertEqual(jobs["build-scan-sign"]["needs"], ["release-config"])
        self.assertEqual(jobs["verify-upstream"]["needs"], ["release-config"])
        self.assertEqual(
            jobs["verify-upstream"]["strategy"]["matrix"],
            "${{ fromJSON(needs.release-config.outputs.matrix) }}",
        )

    def test_reviewed_upstream_pins_are_validated_before_builds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "github-output"
            result = subprocess.run(
                [
                    sys.executable,
                    str(UPSTREAM_CONFIG_VALIDATOR),
                    str(UPSTREAM_CONFIG),
                    "--github-output",
                    str(output),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            matrix = json.loads(output.read_text(encoding="utf-8").split("=", 1)[1])
            self.assertEqual(
                {item["values_key"] for item in matrix["include"]},
                {"IMAGE_APISIX", "IMAGE_OAUTH2_PROXY"},
            )

    def test_upstream_pin_validator_rejects_placeholder_digest(self) -> None:
        payload = json.loads(UPSTREAM_CONFIG.read_text(encoding="utf-8"))
        payload["images"][0]["image"] = "apache/apisix@sha256:" + "0" * 64
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "upstream-images.json"
            invalid.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(UPSTREAM_CONFIG_VALIDATOR), str(invalid)],
                check=False,
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("placeholder digest", result.stderr)

    def test_release_workflow_binds_a_dns_safe_execution_id(self) -> None:
        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        for required in (
            'printf \'%s:%s:%s\' "$GITHUB_SHA" "$GITHUB_RUN_ID" "$GITHUB_RUN_ATTEMPT"',
            'release_id="r-${release_id_hash}"',
            "${#release_id} > 39",
            '--arg release_id "$release_id"',
            'schemaVersion: "archideal.release/v2"',
            "releaseId: $release_id",
        ):
            self.assertIn(required, workflow)

    def test_upstream_workflow_performs_registry_and_runtime_checks(self) -> None:
        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        for required in (
            "docker buildx imagetools inspect",
            "--format '{{json .Manifest}}'",
            "--user 636:636",
            "--entrypoint apisix",
            "trusted-proxy-ip skip-auth-route bearer-token-login-fallback",
            "extra-jwt-issuers session-store-type",
        ):
            self.assertIn(required, workflow)
        workloads = list(
            yaml.safe_load_all(
                (ROOT / "deploy/kubernetes/base/workloads.yaml").read_text(
                    encoding="utf-8"
                )
            )
        )
        oauth = next(
            document
            for document in workloads
            if document
            and document.get("metadata", {}).get("name") == "oauth2-proxy"
        )
        configured_flags = {
            argument[2:].split("=", 1)[0]
            for argument in oauth["spec"]["template"]["spec"]["containers"][0]["args"]
            if argument.startswith("--")
        }
        verifier = VERIFY.read_text(encoding="utf-8")
        self.assertEqual(len(configured_flags), 36)
        for flag in configured_flags:
            self.assertIn(flag, workflow)
            self.assertIn(f'"{flag}"', verifier)

    def build_release(self, root: Path) -> dict[str, Path]:
        policy = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
        source_root = root / "source"
        source_policy = source_root / "deploy/kubernetes/supply-chain-policy.yaml"
        source_policy.parent.mkdir(parents=True)
        shutil.copyfile(POLICY, source_policy)
        for command in (
            ["git", "init", "--quiet", str(source_root)],
            ["git", "-C", str(source_root), "config", "user.name", "Release Test"],
            ["git", "-C", str(source_root), "config", "user.email", "release@test.invalid"],
            ["git", "-C", str(source_root), "add", "."],
            ["git", "-C", str(source_root), "commit", "--quiet", "-m", "release"],
        ):
            subprocess.run(command, check=True, capture_output=True, text=True)
        revision = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        values = yaml.safe_load(EXAMPLE_VALUES.read_text(encoding="utf-8"))
        replacements = {
            "PUBLIC_HOST": "deal.prod.internal.corp",
            "SECRET_PREFIX": "corp/archideal/production",
            "OIDC_ISSUER_URL": "https://identity.prod.internal.corp/realms/archideal",
            "OIDC_INTROSPECTION_URL": "https://identity.prod.internal.corp/oauth2/introspect",
            "KAFKA_BOOTSTRAP_SERVERS": (
                "kafka-0.prod.internal.corp:9093,kafka-1.prod.internal.corp:9093,"
                "kafka-2.prod.internal.corp:9093"
            ),
            "MQTT_HOST": "mqtt.prod.internal.corp",
            "POSTGRES_METADATA_HOST": "metadata-postgres.prod.internal.corp",
            "POSTGRES_DATA_HOST": "data-postgres.prod.internal.corp",
            "VALKEY_HOST": "valkey.prod.internal.corp",
            "ETCD_ENDPOINT_1": "https://etcd-0.prod.internal.corp:2379",
            "ETCD_ENDPOINT_2": "https://etcd-1.prod.internal.corp:2379",
            "ETCD_ENDPOINT_3": "https://etcd-2.prod.internal.corp:2379",
            "ETCD_TLS_SERVER_NAME": "etcd.prod.internal.corp",
            "OTEL_COLLECTOR_HTTP_ENDPOINT": "https://otel.prod.internal.corp/v1/traces",
        }
        values.update(replacements)
        for index, (values_key, image_policy) in enumerate(
            policy["images"].items(), start=1
        ):
            digest = hashlib.sha256(f"image-{index}".encode()).hexdigest()
            values[values_key] = f"{image_policy['repository']}@sha256:{digest}"
        values_path = root / "values.yaml"
        values_path.write_text(yaml.safe_dump(values, sort_keys=False), encoding="utf-8")

        evidence_dir = root / "evidence"
        evidence_dir.mkdir()
        used_files: dict[str, str] = {}

        def evidence(name: str, content: dict) -> dict[str, str]:
            path = evidence_dir / name
            path.write_text(
                json.dumps(content, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            used_files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            return {"file": name, "sha256": used_files[name]}

        def text_evidence(name: str, content: str) -> dict[str, str]:
            path = evidence_dir / name
            path.write_text(content, encoding="utf-8")
            used_files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            return {"file": name, "sha256": used_files[name]}

        workflow = {
            "path": ".github/workflows/release-images.yml",
            "ref": "refs/heads/main",
            "runId": "123456789",
            "runAttempt": "1",
            "event": "push",
        }
        images = []
        for values_key, image_policy in policy["images"].items():
            component = image_policy["component"]
            sbom = evidence(
                f"sbom-{component}.cdx.json",
                {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": []},
            )
            scan = evidence(
                f"trivy-{component}.sarif",
                {
                    "version": "2.1.0",
                    "runs": [
                        {
                            "tool": {"driver": {"name": "Trivy"}},
                            "results": [],
                        }
                    ],
                },
            )
            if image_policy["kind"] == "first-party":
                provenance = evidence(
                    f"provenance-{component}.json",
                    {
                        "buildDefinition": {
                            "buildType": (
                                "https://github.com/Attestations/"
                                "GitHubActionsWorkflow@v1"
                            ),
                            "externalParameters": {
                                "repository": "Smartappli/ArchiDEAL",
                                "revision": revision,
                                "workflow": ".github/workflows/release-images.yml",
                                "context": image_policy["context"],
                                "dockerfile": image_policy["dockerfile"],
                                "platform": "linux/amd64",
                            },
                            "internalParameters": {},
                            "resolvedDependencies": [
                                {
                                    "uri": "git+https://github.com/Smartappli/ArchiDEAL",
                                    "digest": {"gitCommit": revision},
                                }
                            ],
                        },
                        "runDetails": {
                            "builder": {
                                "id": "https://github.com/docker/build-push-action"
                            },
                            "metadata": {
                                "invocationId": (
                                    "https://github.com/Smartappli/ArchiDEAL/"
                                    "actions/runs/123456789/attempts/1"
                                )
                            },
                        },
                    },
                )
                signature_bundle = evidence(
                    f"signature-{component}.sigstore.json",
                    {
                        "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                        "verificationMaterial": {"tlogEntries": [{"logIndex": "1"}]},
                        "messageSignature": {
                            "messageDigest": {
                                "algorithm": "SHA2_256",
                                "digest": "AA==",
                            },
                            "signature": "AA==",
                        },
                    },
                )
                sbom_bundle = evidence(
                    f"attestation-cyclonedx-{component}.sigstore.json",
                    {
                        "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                        "verificationMaterial": {"tlogEntries": [{"logIndex": "2"}]},
                        "dsseEnvelope": {
                            "payload": "AA==",
                            "payloadType": "application/vnd.in-toto+json",
                            "signatures": [{"sig": "AA=="}],
                        },
                    },
                )
                provenance_bundle = evidence(
                    f"attestation-provenance-{component}.sigstore.json",
                    {
                        "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                        "verificationMaterial": {"tlogEntries": [{"logIndex": "3"}]},
                        "dsseEnvelope": {
                            "payload": "AA==",
                            "payloadType": "application/vnd.in-toto+json",
                            "signatures": [{"sig": "AA=="}],
                        },
                    },
                )
                images.append(
                    {
                        "valuesKey": values_key,
                        "component": component,
                        "kind": "first-party",
                        "reference": values[values_key],
                        "revision": revision,
                        "evidence": {
                            "signature": {
                                "issuer": "https://token.actions.githubusercontent.com",
                                "identity": (
                                    "https://github.com/Smartappli/ArchiDEAL/"
                                    ".github/workflows/release-images.yml@refs/heads/main"
                                ),
                            },
                            "attestations": ["cyclonedx", "slsaprovenance1"],
                            "scanPolicy": (
                                "trivy:HIGH,CRITICAL:no-unfixed-exception"
                            ),
                            "sbom": sbom,
                            "scan": scan,
                            "provenance": provenance,
                            "signatureBundle": signature_bundle,
                            "sbomAttestationBundle": sbom_bundle,
                            "provenanceAttestationBundle": provenance_bundle,
                        },
                    }
                )
            else:
                source_tag = image_policy["minimumVersion"]
                if values_key == "IMAGE_OAUTH2_PROXY":
                    source_tag = "v" + source_tag
                source_release = image_policy["sourceReleasePrefix"] + source_tag
                approved_tag = source_tag + image_policy["imageTagSuffix"]
                resolved_digest = "sha256:" + values[values_key].rsplit(
                    "@sha256:", 1
                )[1]
                registry_tag_proof = evidence(
                    f"registry-tag-proof-{component}.json",
                    {
                        "schemaVersion": "archideal.registry-tag-proof/v1",
                        "component": component,
                        "sourceRelease": source_release,
                        "sourceTag": source_tag,
                        "approvedImageTag": approved_tag,
                        "taggedReference": (
                            f"{image_policy['repository']}:{approved_tag}"
                        ),
                        "resolvedDigest": resolved_digest,
                        "immutableReference": values[values_key],
                        "registryManifest": {
                            "schemaVersion": 2,
                            "mediaType": "application/vnd.oci.image.index.v1+json",
                            "digest": resolved_digest,
                            "size": 1234,
                            "manifests": [],
                        },
                    },
                )
                if values_key == "IMAGE_APISIX":
                    runtime_content = (
                        f"Apache APISIX version {image_policy['minimumVersion']}\n"
                    )
                else:
                    runtime_content = "\n".join(
                        f"      --{flag} value"
                        for flag in (
                            "provider",
                            "oidc-issuer-url",
                            "oidc-groups-claim",
                            "oidc-extra-audience",
                            "allowed-group",
                            "scope",
                            "code-challenge-method",
                            "email-domain",
                            "reverse-proxy",
                            "upstream",
                            "http-address",
                            "metrics-address",
                            "redirect-url",
                            "proxy-prefix",
                            "skip-provider-button",
                            "silence-ping-logging",
                            "trusted-proxy-ip",
                            "skip-auth-route",
                            "bearer-token-login-fallback",
                            "extra-jwt-issuers",
                            "session-store-type",
                            "skip-jwt-bearer-tokens",
                            "pass-authorization-header",
                            "set-authorization-header",
                            "pass-access-token",
                            "set-xauthrequest",
                            "pass-user-headers",
                            "cookie-name",
                            "cookie-path",
                            "cookie-secure",
                            "cookie-httponly",
                            "cookie-samesite",
                            "cookie-refresh",
                            "cookie-expire",
                            "cookie-csrf-per-request",
                            "cookie-csrf-expire",
                        )
                    ) + "\n"
                runtime_output = text_evidence(
                    f"runtime-output-{component}.txt", runtime_content
                )
                review = evidence(
                    f"upstream-review-{component}.json",
                    {
                        "schemaVersion": "archideal.upstream-review/v2",
                        "component": component,
                        "reference": values[values_key],
                        "sourceRepository": image_policy["sourceRepository"],
                        "buildRepository": image_policy["buildRepository"],
                        "sourceRelease": source_release,
                        "approvedImageTag": approved_tag,
                        "checks": {
                            "officialImageRepository": True,
                            "digestPinned": True,
                            "sourceVersionAtLeast": image_policy["minimumVersion"],
                            "registryTagResolvesToDigest": True,
                            "runtimeCompatibility": image_policy["runtimeContract"],
                            "independentTrivyScan": "HIGH,CRITICAL",
                            "independentCycloneDxSbom": True,
                            "upstreamCryptographicSignature": "not-assumed",
                        },
                    },
                )
                images.append(
                    {
                        "valuesKey": values_key,
                        "component": component,
                        "kind": "upstream",
                        "reference": values[values_key],
                        "sourceRepository": image_policy["sourceRepository"],
                        "buildRepository": image_policy["buildRepository"],
                        "sourceRelease": source_release,
                        "evidence": {
                            "scanPolicy": (
                                "trivy:HIGH,CRITICAL:no-unfixed-exception"
                            ),
                            "sbom": sbom,
                            "scan": scan,
                            "upstreamReview": review,
                            "registryTagProof": registry_tag_proof,
                            "runtimeOutput": runtime_output,
                        },
                    }
                )

        manifest = {
            "schemaVersion": "archideal.release/v2",
            "repository": "Smartappli/ArchiDEAL",
            "revision": revision,
            "releaseId": values["RELEASE_ID"],
            "generatedAt": "2026-07-18T02:00:00Z",
            "workflow": workflow,
            "policySha256": hashlib.sha256(source_policy.read_bytes()).hexdigest(),
            "images": sorted(images, key=lambda item: item["valuesKey"]),
        }
        manifest_path = root / "release-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
        )
        bundle_path = root / "release-manifest.sigstore.json"
        bundle_path.write_text("{}\n", encoding="utf-8")
        cosign_log = root / "cosign.log"
        fake_cosign = root / "cosign"
        fake_cosign.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >> \"$COSIGN_LOG\"\n"
            "exit \"${COSIGN_EXIT:-0}\"\n",
            encoding="utf-8",
        )
        fake_cosign.chmod(0o755)
        return {
            "values": values_path,
            "manifest": manifest_path,
            "bundle": bundle_path,
            "evidence": evidence_dir,
            "cosign": fake_cosign,
            "cosign_log": cosign_log,
            "source": source_root,
            "policy": source_policy,
        }

    def verify(
        self, fixture: dict[str, Path], **environment: str
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update(environment)
        env["COSIGN_LOG"] = str(fixture["cosign_log"])
        return subprocess.run(
            [
                sys.executable,
                str(VERIFY),
                "--values",
                str(fixture["values"]),
                "--manifest",
                str(fixture["manifest"]),
                "--bundle",
                str(fixture["bundle"]),
                "--evidence-dir",
                str(fixture["evidence"]),
                "--source-root",
                str(fixture["source"]),
                "--policy",
                str(fixture["policy"]),
                "--cosign",
                str(fixture["cosign"]),
            ],
            cwd=ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    @staticmethod
    def replace_signed_evidence(
        fixture: dict[str, Path],
        *,
        values_key: str,
        evidence_key: str,
        content: str,
    ) -> None:
        manifest = json.loads(fixture["manifest"].read_text(encoding="utf-8"))
        image = next(
            item for item in manifest["images"] if item["valuesKey"] == values_key
        )
        record = image["evidence"][evidence_key]
        path = fixture["evidence"] / record["file"]
        path.write_text(content, encoding="utf-8")
        record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        fixture["manifest"].write_text(
            json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
        )

    def test_verifies_all_evidence_and_first_party_attestations(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = self.build_release(Path(temporary_directory))
            result = self.verify(fixture)
            self.assertEqual(result.returncode, 0, result.stderr)
            commands = fixture["cosign_log"].read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(commands), 25)
        self.assertEqual(sum(command.startswith("verify-blob ") for command in commands), 1)
        self.assertEqual(sum(command.startswith("verify ") for command in commands), 8)
        self.assertEqual(
            sum(command.startswith("verify-attestation ") for command in commands),
            16,
        )
        self.assertIn(" --bundle ", f" {commands[0]} ")
        for command in commands[1:]:
            # Cosign v3 has no detached --bundle input for image verification;
            # these commands must verify the exact digest from the registry.
            self.assertNotIn(" --bundle ", f" {command} ")
            for claim in (
                "--certificate-github-workflow-repository Smartappli/ArchiDEAL",
                "--certificate-github-workflow-ref refs/heads/main",
                "--certificate-github-workflow-sha ",
                "--certificate-github-workflow-trigger push",
            ):
                self.assertIn(claim, command)
        self.assertEqual(
            sum("--type cyclonedx" in command for command in commands),
            8,
        )
        self.assertEqual(
            sum("--type slsaprovenance1" in command for command in commands),
            8,
        )

    def test_rejects_values_digest_not_in_signed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = self.build_release(Path(temporary_directory))
            values = yaml.safe_load(fixture["values"].read_text(encoding="utf-8"))
            repository = values["IMAGE_DEALHOST"].split("@", 1)[0]
            values["IMAGE_DEALHOST"] = f"{repository}@sha256:{'f' * 64}"
            fixture["values"].write_text(
                yaml.safe_dump(values, sort_keys=False), encoding="utf-8"
            )
            result = self.verify(fixture)
        self.assertEqual(result.returncode, 2)
        self.assertIn("signed release", result.stderr)

    def test_rejects_values_release_id_not_in_signed_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = self.build_release(Path(temporary_directory))
            values = yaml.safe_load(fixture["values"].read_text(encoding="utf-8"))
            values["RELEASE_ID"] = "r-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
            fixture["values"].write_text(
                yaml.safe_dump(values, sort_keys=False), encoding="utf-8"
            )
            result = self.verify(fixture)
        self.assertEqual(result.returncode, 2)
        self.assertIn("RELEASE_ID does not match the signed releaseId", result.stderr)

    def test_rejects_invalid_signed_release_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = self.build_release(Path(temporary_directory))
            manifest = json.loads(fixture["manifest"].read_text(encoding="utf-8"))
            manifest["releaseId"] = "INVALID_RELEASE"
            fixture["manifest"].write_text(
                json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
            )
            result = self.verify(fixture)
        self.assertEqual(result.returncode, 2)
        self.assertIn("releaseId must be a lowercase DNS label", result.stderr)

    def test_rejects_manifest_without_signed_release_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = self.build_release(Path(temporary_directory))
            manifest = json.loads(fixture["manifest"].read_text(encoding="utf-8"))
            del manifest["releaseId"]
            fixture["manifest"].write_text(
                json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
            )
            result = self.verify(fixture)
        self.assertEqual(result.returncode, 2)
        self.assertIn("release manifest keys mismatch", result.stderr)

    def test_rejects_tampered_evidence_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = self.build_release(Path(temporary_directory))
            (fixture["evidence"] / "sbom-dealhost.cdx.json").write_text(
                '{"bomFormat":"tampered"}\n', encoding="utf-8"
            )
            result = self.verify(fixture)
        self.assertEqual(result.returncode, 2)
        self.assertIn("digest mismatch", result.stderr)

    def test_rejects_signed_scan_evidence_with_vulnerabilities(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = self.build_release(Path(temporary_directory))
            scan_path = fixture["evidence"] / "trivy-dealhost.sarif"
            scan_path.write_text(
                json.dumps(
                    {
                        "version": "2.1.0",
                        "runs": [
                            {
                                "tool": {"driver": {"name": "Trivy"}},
                                "results": [{"ruleId": "CVE-2099-0001"}],
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            manifest = json.loads(fixture["manifest"].read_text(encoding="utf-8"))
            dealhost = next(
                image for image in manifest["images"] if image["valuesKey"] == "IMAGE_DEALHOST"
            )
            dealhost["evidence"]["scan"]["sha256"] = hashlib.sha256(
                scan_path.read_bytes()
            ).hexdigest()
            fixture["manifest"].write_text(
                json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
            )
            result = self.verify(fixture)
        self.assertEqual(result.returncode, 2)
        self.assertIn("HIGH/CRITICAL vulnerability", result.stderr)

    def test_rejects_signed_registry_tag_proof_for_another_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = self.build_release(Path(temporary_directory))
            proof_path = fixture["evidence"] / "registry-tag-proof-apisix.json"
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            proof["resolvedDigest"] = f"sha256:{'f' * 64}"
            self.replace_signed_evidence(
                fixture,
                values_key="IMAGE_APISIX",
                evidence_key="registryTagProof",
                content=json.dumps(proof, sort_keys=True) + "\n",
            )
            result = self.verify(fixture)
        self.assertEqual(result.returncode, 2)
        self.assertIn("bind the approved source tag", result.stderr)

    def test_rejects_oauth_runtime_without_sensitive_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = self.build_release(Path(temporary_directory))
            output_path = fixture["evidence"] / "runtime-output-oauth2-proxy.txt"
            output = output_path.read_text(encoding="utf-8").replace(
                "      --trusted-proxy-ip value\n", ""
            )
            self.replace_signed_evidence(
                fixture,
                values_key="IMAGE_OAUTH2_PROXY",
                evidence_key="runtimeOutput",
                content=output,
            )
            result = self.verify(fixture)
        self.assertEqual(result.returncode, 2)
        self.assertIn("trusted-proxy-ip", result.stderr)

    def test_rejects_upstream_source_below_minimum(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = self.build_release(Path(temporary_directory))
            manifest = json.loads(fixture["manifest"].read_text(encoding="utf-8"))
            oauth = next(
                image
                for image in manifest["images"]
                if image["valuesKey"] == "IMAGE_OAUTH2_PROXY"
            )
            oauth["sourceRelease"] = (
                "https://github.com/oauth2-proxy/oauth2-proxy/releases/tag/v7.15.2"
            )
            fixture["manifest"].write_text(
                json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
            )
            result = self.verify(fixture)
        self.assertEqual(result.returncode, 2)
        self.assertIn("below the approved minimum", result.stderr)

    def test_rejects_unapproved_image_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = self.build_release(Path(temporary_directory))
            values = yaml.safe_load(fixture["values"].read_text(encoding="utf-8"))
            values["IMAGE_APISIX"] = f"registry.example.org/apisix@sha256:{'e' * 64}"
            fixture["values"].write_text(
                yaml.safe_dump(values, sort_keys=False), encoding="utf-8"
            )
            result = self.verify(fixture)
        self.assertEqual(result.returncode, 2)
        self.assertIn("repository approved", result.stderr)

    def test_cosign_failure_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = self.build_release(Path(temporary_directory))
            result = self.verify(fixture, COSIGN_EXIT="1")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Cosign verification failed", result.stderr)

    def test_rejects_dirty_release_source_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            fixture = self.build_release(Path(temporary_directory))
            (fixture["source"] / "untracked-change.txt").write_text(
                "not part of the signed revision\n", encoding="utf-8"
            )
            result = self.verify(fixture)
        self.assertEqual(result.returncode, 2)
        self.assertIn("clean tree", result.stderr)


if __name__ == "__main__":
    unittest.main()
