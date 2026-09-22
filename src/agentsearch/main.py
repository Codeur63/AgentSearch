import asyncio
import uuid
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from agentsearch.llm import ask_llm
from temporalio.client import Client 
from temporalio.worker import Worker
from agentsearch.tools.search import search_web
from agentsearch.worklows.workflow import ContentWorkflow
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__) 

async def main():
    try:
        logger.info("Connexion au serveur Temporal")
        client = await Client.connect("localhost:7233")
        logger.info("Connexion reussis a Temporal ")
    except Exception as e:
        logger.error("Erreur inattendue est survenue")

    worker = Worker(
        client,
        task_queue="agent-search",
        workflows=[ContentWorkflow],
        activities=[search_web, ask_llm]
    )

    print("Worker démarré...")
    worker_id = f"test-recherch-agent-{uuid.uuid4()}"

    worker_task = asyncio.create_task(worker.run())

    try:
        while True:
            question = input("Human : ")
            if question.lower() in {'exit', 'quit', 'q'}:
                print("A bientot")
                break
            

            resultat_search = await client.execute_workflow(
                ContentWorkflow.run,
                question,
                id=worker_id,
                task_queue="agent-search"
            )


            print(f"Agent : {resultat_search}")
            print("="*40)
    finally:
        worker_task.cancel() 

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error("Une erreur est survenue")    