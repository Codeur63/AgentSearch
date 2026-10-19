
import asyncio
import logging
import os
from agentsearch import settings as _settings
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker
from temporalio.contrib.pydantic import pydantic_data_converter

from agentsearch.tools.scraper import extract_content


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Connexion au serveur Temporal...")

    client = await Client.connect(
        os.getenv("TEMPORAL_ADDRESS", "localhost:7233"),
        data_converter=pydantic_data_converter,
    )

    logger.info("Connexion Temporal établie.")

    with ThreadPoolExecutor(max_workers=4) as executor:
        worker = Worker(
            client,
            task_queue="agent-scraper",
            workflows=[],
            activities=[extract_content],
            activity_executor=executor,
            max_concurrent_activities=4,
        )

        logger.info(
            "Worker scraper démarré sur la Task Queue : agent-scraper"
        )

        await worker.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Arrêt du Worker scraper.")
    except Exception:
        logger.exception("Erreur du Worker scraper.")
        raise
