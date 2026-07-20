from __future__ import annotations

from copy import deepcopy
import re

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from apps.hosting.models import RuntimeEnvironment


PRODUCTION_SLUG = "production"
LOGICAL_SECRET_REFERENCE_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
PRODUCTION_FIELDS: dict[str, object] = {
    "name": "Production",
    "description": "Isolated Kubernetes production environment managed by DEALHost.",
    "orchestrator": "kubernetes",
    "enabled": True,
    "capabilities": {
        "start_stop": True,
        "restart": True,
        "scaling": {
            "fixed": {"min_replicas": 1, "max_replicas": 10},
            "autoscaling": {
                "enabled": True,
                "min_replicas": 1,
                "max_replicas": 10,
            },
        },
        "logs": {"max_lines": 1000, "max_bytes": 262144},
        "domains": False,
        "network_egress": False,
    },
    "policy": {
        "requires_image_digest": True,
        "allowed_registries": ["ghcr.io/smartappli/"],
        "allowed_secret_refs": [],
        "stateless_only": True,
    },
}


class Command(BaseCommand):
    help = (
        "Provision the production RuntimeEnvironment used by the isolated "
        "DEALHost Kubernetes runtime controller."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        secret_group = parser.add_mutually_exclusive_group()
        secret_group.add_argument(
            "--allowed-secret-ref",
            action="append",
            default=None,
            dest="allowed_secret_refs",
            metavar="NAME",
            help=(
                "Replace the allowlist with canonical logical runtime Secret "
                "references. The isolated controller resolves Kubernetes names; "
                "repeat this option for every operator-catalogued reference."
            ),
        )
        secret_group.add_argument(
            "--clear-allowed-secret-refs",
            action="store_true",
            help="Explicitly replace the logical runtime Secret allowlist with empty.",
        )

    def handle(self, *args, **options) -> None:
        requested_refs = options["allowed_secret_refs"]
        if requested_refs is not None and not _valid_secret_refs(requested_refs):
            raise CommandError(
                "--allowed-secret-ref must contain at most 100 unique canonical "
                "logical Secret references."
            )
        if requested_refs is not None:
            requested_refs = sorted(requested_refs)
        elif options["clear_allowed_secret_refs"]:
            requested_refs = []

        with transaction.atomic():
            creation_fields = _desired_fields(requested_refs or [])
            environment, created = (
                RuntimeEnvironment.objects.select_for_update().get_or_create(
                    slug=PRODUCTION_SLUG,
                    defaults={**creation_fields, "revision": 1},
                )
            )
            changed_fields: list[str] = []
            if not created:
                if requested_refs is None:
                    policy = environment.policy
                    existing_refs = (
                        policy.get("allowed_secret_refs")
                        if isinstance(policy, dict)
                        else None
                    )
                    effective_refs = (
                        sorted(existing_refs)
                        if _valid_secret_refs(existing_refs)
                        else []
                    )
                else:
                    effective_refs = requested_refs
                desired_fields = _desired_fields(effective_refs)
                for field_name, desired_value in desired_fields.items():
                    if getattr(environment, field_name) != desired_value:
                        setattr(environment, field_name, desired_value)
                        changed_fields.append(field_name)
                if changed_fields:
                    environment.revision += 1
                    environment.save(
                        update_fields=[*changed_fields, "revision", "updated_at"]
                    )

        if created:
            action = "created"
        elif changed_fields:
            action = "updated"
        else:
            action = "unchanged"
        self.stdout.write(
            self.style.SUCCESS(
                f"Runtime environment '{PRODUCTION_SLUG}' {action} "
                f"at revision {environment.revision}."
            )
        )


def _valid_secret_refs(value: object) -> bool:
    return (
        isinstance(value, list)
        and len(value) <= 100
        and all(
            isinstance(item, str)
            and bool(LOGICAL_SECRET_REFERENCE_PATTERN.fullmatch(item))
            for item in value
        )
        and len(set(value)) == len(value)
    )


def _desired_fields(allowed_secret_refs: list[str]) -> dict[str, object]:
    desired_fields = deepcopy(PRODUCTION_FIELDS)
    policy = desired_fields["policy"]
    assert isinstance(policy, dict)
    policy["allowed_secret_refs"] = allowed_secret_refs
    return desired_fields
