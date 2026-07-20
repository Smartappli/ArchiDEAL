from __future__ import annotations

import ipaddress
import os
import socket
import uuid

from django.core.management.base import BaseCommand, CommandParser

from apps.hosting.runtime_observability import (
    RuntimeWorkerHealth,
    RuntimeWorkerMonitor,
)
from apps.hosting.runtime_worker import RuntimeOperationProcessor


class Command(BaseCommand):
    help = "Process durable runtime-controller operations from an isolated worker."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-seconds", type=float, default=2.0)
        parser.add_argument("--worker-id", default="")
        parser.add_argument(
            "--metrics-bind",
            default=os.environ.get("DEALHOST_RUNTIME_WORKER_METRICS_BIND", "127.0.0.1"),
        )
        parser.add_argument(
            "--metrics-port",
            type=int,
            default=int(os.environ.get("DEALHOST_RUNTIME_WORKER_METRICS_PORT", "9102")),
        )
        parser.add_argument(
            "--heartbeat-timeout-seconds",
            type=float,
            default=float(
                os.environ.get(
                    "DEALHOST_RUNTIME_WORKER_HEARTBEAT_TIMEOUT_SECONDS", "90"
                )
            ),
        )

    def handle(self, *args, **options) -> None:
        poll_seconds = options["poll_seconds"]
        if not 0.1 <= poll_seconds <= 60:
            raise ValueError("--poll-seconds must be between 0.1 and 60.")
        metrics_bind = options["metrics_bind"]
        try:
            bind_address = ipaddress.ip_address(metrics_bind)
        except ValueError as exc:
            raise ValueError("--metrics-bind must be an IPv4 address literal.") from exc
        if bind_address.version != 4:
            raise ValueError("--metrics-bind must be an IPv4 address literal.")
        metrics_port = options["metrics_port"]
        if not 1 <= metrics_port <= 65535:
            raise ValueError("--metrics-port must be between 1 and 65535.")
        worker_id = options["worker_id"] or (
            f"{socket.gethostname()}-{uuid.uuid4().hex[:12]}"
        )
        processor = RuntimeOperationProcessor(worker_id=worker_id)
        if options["once"]:
            processor.run(once=True, poll_seconds=poll_seconds)
            return

        health = RuntimeWorkerHealth(
            heartbeat_timeout_seconds=options["heartbeat_timeout_seconds"]
        )
        monitor = RuntimeWorkerMonitor(
            bind=metrics_bind,
            port=metrics_port,
            health=health,
        )
        monitor.start()
        try:
            processor.run(
                once=False,
                poll_seconds=poll_seconds,
                heartbeat=health.beat,
            )
        finally:
            monitor.stop()
