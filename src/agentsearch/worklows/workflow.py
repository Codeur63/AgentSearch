from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from agentsearch.tools.search import search_web
    from agentsearch.llm import ask_llm


ACTIVITY_TIMEOUT = timedelta(minutes=5)

ACTIVITY_RETRY_POLICY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
)

@workflow.defn
class ContentWorkflow:

    @workflow.run 
    async def run(self, question: str) -> str:

        research_result = await workflow.execute_activity(
            search_web,
            question,
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=ACTIVITY_RETRY_POLICY,
        )

        # ==========================================
        # 2. LLM
        # ==========================================

        response = await workflow.execute_activity(
            ask_llm,
            args=[question, research_result],
            start_to_close_timeout=ACTIVITY_TIMEOUT,
            retry_policy=ACTIVITY_RETRY_POLICY,
        )
        

        return response