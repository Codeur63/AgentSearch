from pydantic import BaseModel

class AgentState(BaseModel):
    question: str
    