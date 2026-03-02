from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional


class TaskStatus(str, Enum):
    PENDING = "pending"
    WRITING = "writing"
    REVIEWING = "reviewing"
    DEPLOYING = "deploying"
    DONE = "done"
    FAILED = "failed"


class CreateTaskRequest(BaseModel):
    repo_url: str = Field(..., description="HTTPS or SSH URL of the git repository")
    requirement: str = Field(..., description="Natural language description of what to build/change")


class TaskStageResult(BaseModel):
    stage: str
    status: str
    data: Optional[dict] = None


class TaskResponse(BaseModel):
    task_id: str
    status: TaskStatus
    repo_url: str
    requirement: str
    stages: list[TaskStageResult] = []
    workflow_id: Optional[str] = None
    error: Optional[str] = None
