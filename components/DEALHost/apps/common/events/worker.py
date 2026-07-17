from __future__ import annotations

import asyncio
import logging

from django.conf import settings
from nats.aio.client import Client as NATS

logger = logging.getLogger(__name__)


async def run_worker() -> None:
    client = NATS()
    await client.connect(settings.NATS["URL"])

    async def handler(msg):
        logger.info("NATS event received on %s", msg.subject)

    await client.subscribe(f"{settings.NATS['SUBJECT_PREFIX']}.>", cb=handler)

    while True:
        await asyncio.sleep(1)


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
