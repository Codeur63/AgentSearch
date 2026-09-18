from pydantic import BaseModel
from datetime import timedelta
from temporalio.common import RetryPolicy

ACTIVITY_RETRY_POLICY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
)

class WorkflowStatus(BaseModel):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    RESEARCHING = "RESEARCHING"
    VERIFY = "VERIFY"
    WRITING = "WRITING"
    QUALITY_CHECK = "QUALITY_CHECK"
    WAITING_HUMAN = "WAITING_HUMAN"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
 
class State(BaseModel):
    task_id : str
    status : WorkflowStatus
    question : str
    language: str
    plan: list[str]
    research : list[str] 
    research_roung: int
    sources : list[str] 
    claims : list[str]
    verify_claims : []
    report : str | None
    article : str | None
    quality_result : str | None