from __future__ import annotations

import socket
import uuid

from django.core.management.base import BaseCommand, CommandParser

from apps.hosting.runtime_worker import RuntimeOperationProcessor


class Command(BaseCommand):
    help = "Process durable runtime-controller operations from an isolated worker."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-seconds", type=float, default=2.0)
        parser.add_argument("--worker-id", default="")

    def handle(self, *args, **options) -> None:
        poll_seconds = options["poll_seconds"]
        if not 0.1 <= poll_seconds <= 60:
            raise ValueError("--poll-seconds must be between 0.1 and 60.")
        worker_id = options["worker_id"] or (
            f"{socket.gethostname()}-{uuid.uuid4().hex[:12]}"
        )
        processor = RuntimeOperationProcessor(worker_id=worker_id)
        processor.run(once=options["once"], poll_seconds=poll_seconds)
