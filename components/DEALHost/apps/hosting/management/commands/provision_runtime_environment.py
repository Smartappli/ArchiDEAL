from __future__ import annotations

from copy import deepcopy
import re

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from apps.hosting.models import RuntimeEnvironment


PRODUCTION_SLUG = "production"
SECRET_REFERENCE_PATTERN = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
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
        parser.add_argument(
            "--allowed-secret-ref",
            action="append",
            default=[],
            dest="allowed_secret_refs",
            metavar="NAME",
            help=(
                "Allow a canonical Kubernetes Secret name. Repeat this option for "
                "each explicitly provisioned application secret."
            ),
        )

    def handle(self, *args, **options) -> None:
        desired_fields = deepcopy(PRODUCTION_FIELDS)
        secret_refs = options["allowed_secret_refs"]
        if (
            len(secret_refs) > 100
            or any(
                not isinstance(item, str)
                or not SECRET_REFERENCE_PATTERN.fullmatch(item)
                for item in secret_refs
            )
            or len(set(secret_refs)) != len(secret_refs)
        ):
            raise CommandError(
                "--allowed-secret-ref must contain at most 100 unique canonical "
                "Kubernetes Secret names."
            )
        policy = desired_fields["policy"]
        assert isinstance(policy, dict)
        policy["allowed_secret_refs"] = sorted(secret_refs)
        with transaction.atomic():
            environment, created = (
                RuntimeEnvironment.objects.select_for_update().get_or_create(
                    slug=PRODUCTION_SLUG,
                    defaults={**desired_fields, "revision": 1},
                )
            )
            changed_fields: list[str] = []
            if not created:
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
