"""Workers réutilisables, indépendants de l'interface terminal."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import AsyncExitStack, asynccontextmanager

from temporalio.client import Client
from temporalio.worker import Worker

from agentsearch.orchestration.activities import MAIN_ACTIVITIES
from agentsearch.orchestration.workflows import ContentWorkflow, MAIN_TASK_QUEUE, SCRAPER_TASK_QUEUE
from agentsearch.tools.scraper import extract_content


@asynccontextmanager
async def running_workers(client: Client):
    with ThreadPoolExecutor(max_workers=8) as executor:
        async with AsyncExitStack() as stack:
            await stack.enter_async_context(Worker(
                client, task_queue=MAIN_TASK_QUEUE, workflows=[ContentWorkflow],
                activities=MAIN_ACTIVITIES, activity_executor=executor, max_concurrent_activities=4,
            ))
            await stack.enter_async_context(Worker(
                client, task_queue=SCRAPER_TASK_QUEUE, activities=[extract_content],
                activity_executor=executor, max_concurrent_activities=4,
            ))
            yield
