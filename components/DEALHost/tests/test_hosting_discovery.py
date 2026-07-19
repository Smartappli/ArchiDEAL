import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import TestCase, override_settings

from apps.hosting.discovery import (
    auto_discover_tools_and_applications,
    public_autodiscovery_error,
)
from apps.hosting.models import HostedApplication, Module, Tool


class HostingDiscoveryTests(TestCase):
    def test_autodiscover_creates_modules_from_manifests(self):
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "modules").mkdir(parents=True)
            (base / "modules" / "flink-runtime.json").write_text(
                json.dumps(
                    {
                        "name": "DEALIoT Flink Runtime",
                        "slug": "flink-runtime",
                        "image": "ghcr.io/smartappli/dealiot-flink-pyflink:sha-test",
                        "repository_owner": "Smartappli",
                        "repository_name": "DEALIoT",
                        "source_path": "pipelines",
                        "deployment_target": "kubernetes",
                        "public_path": "/dealiot/flink",
                        "upstream_host": "flink-jobmanager",
                        "upstream_port": 8081,
                        "contract_topics": ["raw.sensor", "state.latest"],
                    },
                ),
                encoding="utf-8",
            )

            report = auto_discover_tools_and_applications(manifests_dir=base)

        self.assertEqual(report.modules_created, 1)
        self.assertEqual(report.errors, [])
        module = Module.objects.get(slug="flink-runtime")
        self.assertEqual(module.repository_owner, "Smartappli")
        self.assertEqual(module.repository_name, "DEALIoT")
        self.assertEqual(module.source_path, "pipelines")
        self.assertEqual(module.deployment_target, "kubernetes")
        self.assertEqual(module.public_path, "/dealiot/flink")
        self.assertEqual(module.upstream_host, "flink-jobmanager")
        self.assertEqual(module.upstream_port, 8081)
        self.assertEqual(module.contract_topics, ["raw.sensor", "state.latest"])

    def test_autodiscover_creates_tools_and_applications_from_manifests(self):
        module = Module.objects.create(
            name="Core",
            slug="module-core",
            image="ghcr.io/dealiot/module-core:latest",
            branch="main",
        )

        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "tools").mkdir(parents=True)
            (base / "applications").mkdir(parents=True)
            (base / "tools" / "backoffice.json").write_text(
                json.dumps(
                    {
                        "name": "Backoffice",
                        "slug": "backoffice",
                        "description": "Tool for operations",
                        "module_slugs": ["module-core"],
                        "version": "1.0.0",
                    },
                ),
                encoding="utf-8",
            )
            (base / "applications" / "storefront.json").write_text(
                json.dumps(
                    {
                        "name": "Storefront",
                        "slug": "storefront",
                        "description": "Customer app",
                        "module_slugs": ["module-core"],
                        "version": "2.1.0",
                    },
                ),
                encoding="utf-8",
            )

            report = auto_discover_tools_and_applications(manifests_dir=base)

        self.assertEqual(report.tools_created, 1)
        self.assertEqual(report.applications_created, 1)
        self.assertEqual(report.tool_versions_created, 1)
        self.assertEqual(report.application_versions_created, 1)
        self.assertEqual(report.errors, [])

        tool = Tool.objects.get(slug="backoffice")
        application = HostedApplication.objects.get(slug="storefront")
        self.assertEqual(list(tool.modules.all()), [module])
        self.assertEqual(list(application.modules.all()), [module])
        self.assertEqual(tool.current_version, "1.0.0")
        self.assertEqual(application.current_version, "2.1.0")

    def test_autodiscover_exact_version_replay_does_not_republish(self):
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "tools").mkdir(parents=True)
            (base / "applications").mkdir(parents=True)
            (base / "tools" / "backoffice.json").write_text(
                json.dumps(
                    {
                        "name": "Backoffice",
                        "slug": "backoffice",
                        "version": "1.0.0",
                        "version_notes": "Immutable tool release",
                    },
                ),
                encoding="utf-8",
            )
            (base / "applications" / "storefront.json").write_text(
                json.dumps(
                    {
                        "name": "Storefront",
                        "slug": "storefront",
                        "version": "2.1.0",
                        "version_notes": "Immutable application release",
                    },
                ),
                encoding="utf-8",
            )

            first_report = auto_discover_tools_and_applications(manifests_dir=base)
            tool = Tool.objects.get(slug="backoffice")
            application = HostedApplication.objects.get(slug="storefront")
            tool_released_at = tool.released_at
            application_released_at = application.released_at
            application_revision = application.revision

            replay_report = auto_discover_tools_and_applications(manifests_dir=base)

        self.assertEqual(first_report.tool_versions_created, 1)
        self.assertEqual(first_report.application_versions_created, 1)
        self.assertEqual(replay_report.tool_versions_created, 0)
        self.assertEqual(replay_report.application_versions_created, 0)
        self.assertEqual(replay_report.errors, [])
        tool.refresh_from_db()
        application.refresh_from_db()
        self.assertEqual(tool.released_at, tool_released_at)
        self.assertEqual(application.released_at, application_released_at)
        self.assertEqual(application.revision, application_revision)
        self.assertEqual(tool.versions.count(), 1)
        self.assertEqual(application.versions.count(), 1)

    def test_autodiscover_only_revises_application_for_effective_catalog_changes(self):
        module = Module.objects.create(
            name="Core",
            slug="module-core",
            image="registry.example/core:latest",
        )
        application = HostedApplication.objects.create(
            name="Storefront",
            slug="storefront",
            description="Initial metadata",
        )
        application.modules.add(module)

        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "applications").mkdir(parents=True)
            manifest = base / "applications" / "storefront.json"
            manifest.write_text(
                json.dumps(
                    {
                        "name": "Storefront",
                        "slug": "storefront",
                        "description": "Initial metadata",
                        "module_slugs": ["module-core"],
                    },
                ),
                encoding="utf-8",
            )

            auto_discover_tools_and_applications(manifests_dir=base)
            application.refresh_from_db()
            self.assertEqual(application.revision, 1)

            manifest.write_text(
                json.dumps(
                    {
                        "name": "Storefront",
                        "slug": "storefront",
                        "description": "Changed metadata",
                        "module_slugs": [],
                    },
                ),
                encoding="utf-8",
            )
            auto_discover_tools_and_applications(manifests_dir=base)
            application.refresh_from_db()
            self.assertEqual(application.revision, 2)
            self.assertEqual(application.description, "Changed metadata")
            self.assertFalse(application.modules.exists())

            auto_discover_tools_and_applications(manifests_dir=base)

        application.refresh_from_db()
        self.assertEqual(application.revision, 2)

    def test_autodiscover_rejects_changed_metadata_for_existing_versions(self):
        tool = Tool.objects.create(
            name="Backoffice",
            slug="backoffice",
            current_version="1.0.0",
        )
        tool.versions.create(
            version="1.0.0",
            notes="Original tool release",
            source="autodiscovery",
        )
        application = HostedApplication.objects.create(
            name="Storefront",
            slug="storefront",
            current_version="2.1.0",
        )
        application.versions.create(
            version="2.1.0",
            notes="Original application release",
            source="autodiscovery",
        )

        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "tools").mkdir(parents=True)
            (base / "applications").mkdir(parents=True)
            (base / "tools" / "backoffice.json").write_text(
                json.dumps(
                    {
                        "name": "Renamed backoffice",
                        "slug": "backoffice",
                        "version": "1.0.0",
                        "version_notes": "Replacement tool release",
                    },
                ),
                encoding="utf-8",
            )
            (base / "applications" / "storefront.json").write_text(
                json.dumps(
                    {
                        "name": "Renamed storefront",
                        "slug": "storefront",
                        "version": "2.1.0",
                        "version_notes": "Replacement application release",
                    },
                ),
                encoding="utf-8",
            )

            report = auto_discover_tools_and_applications(manifests_dir=base)

        self.assertTrue(report.rolled_back)
        self.assertEqual(report.error_count, 2)
        tool.refresh_from_db()
        application.refresh_from_db()
        self.assertEqual(tool.name, "Backoffice")
        self.assertEqual(application.name, "Storefront")
        self.assertEqual(tool.versions.get().notes, "Original tool release")
        self.assertEqual(
            application.versions.get().notes,
            "Original application release",
        )

    def test_autodiscover_rolls_back_when_module_reference_is_missing(self):
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "tools").mkdir(parents=True)
            (base / "tools" / "broken.json").write_text(
                json.dumps(
                    {
                        "name": "Broken Tool",
                        "slug": "broken-tool",
                        "module_slugs": ["missing-module"],
                        "version": "1.4.2",
                    },
                ),
                encoding="utf-8",
            )

            report = auto_discover_tools_and_applications(manifests_dir=base)

        self.assertEqual(report.tools_created, 0)
        self.assertEqual(report.tool_versions_created, 0)
        self.assertTrue(report.rolled_back)
        self.assertTrue(report.errors)
        self.assertEqual(report.error_count, 1)
        self.assertFalse(Tool.objects.filter(slug="broken-tool").exists())

    def test_autodiscover_rejects_invalid_version(self):
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "applications").mkdir(parents=True)
            (base / "applications" / "bad-version.json").write_text(
                json.dumps(
                    {
                        "name": "BadVersion",
                        "slug": "bad-version",
                        "version": "release-1",
                    },
                ),
                encoding="utf-8",
            )

            report = auto_discover_tools_and_applications(manifests_dir=base)

        self.assertEqual(report.applications_created, 0)
        self.assertTrue(report.rolled_back)
        self.assertEqual(report.errors, [public_autodiscovery_error()])
        self.assertEqual(report.error_count, 1)
        self.assertFalse(HostedApplication.objects.filter(slug="bad-version").exists())

    def test_autodiscover_rejects_a_non_object_json_manifest(self):
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "modules").mkdir(parents=True)
            (base / "modules" / "invalid.json").write_text(
                json.dumps(["not", "an", "object"]),
                encoding="utf-8",
            )

            report = auto_discover_tools_and_applications(manifests_dir=base)

        self.assertTrue(report.rolled_back)
        self.assertEqual(report.errors, [public_autodiscovery_error()])
        self.assertEqual(report.error_count, 1)

    def test_autodiscover_uses_the_configured_project_directory(self):
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            manifests = base / "manifests"
            (manifests / "modules").mkdir(parents=True)
            (manifests / "modules" / "configured-path.json").write_text(
                json.dumps(
                    {
                        "name": "Configured Path",
                        "slug": "configured-path",
                        "image": "example/configured-path:1.0.0",
                    },
                ),
                encoding="utf-8",
            )

            with override_settings(BASE_DIR=base):
                report = auto_discover_tools_and_applications()

        self.assertEqual(report.modules_created, 1)
        self.assertEqual(report.errors, [])
        self.assertTrue(Module.objects.filter(slug="configured-path").exists())
