from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.conf import settings


async def _publish(subject: str, payload: dict[str, Any]) -> None:
    if not settings.NATS["ENABLED"]:
        return

    from nats.aio.client import Client as NATS

    client = NATS()
    await client.connect(settings.NATS["URL"])
    try:
        await client.publish(subject, json.dumps(payload).encode("utf-8"))
        await client.flush()
    finally:
        await client.close()


def publish(subject: str, payload: dict[str, Any]) -> None:
    if not settings.NATS["ENABLED"]:
        return

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_publish(subject=subject, payload=payload))
        return

    # A synchronous API cannot run another loop in the current thread. Execute
    # the publish in a short-lived worker and preserve its error semantics.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="dealhost-nats") as pool:
        pool.submit(asyncio.run, _publish(subject=subject, payload=payload)).result()
