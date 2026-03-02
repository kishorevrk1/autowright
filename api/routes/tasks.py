import uuid
from fastapi import APIRouter, HTTPException
from temporalio.client import Client, WorkflowExecutionStatus

from api.models import CreateTaskRequest, TaskResponse, TaskStatus, TaskStageResult

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def get_temporal_client() -> Client:
    import os
    host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    return await Client.connect(host)


@router.post("", response_model=TaskResponse, status_code=202)
async def create_task(body: CreateTaskRequest):
    task_id = str(uuid.uuid4())
    client = await get_temporal_client()

    handle = await client.start_workflow(
        "DevPipelineWorkflow",
        args=[{"task_id": task_id, "repo_url": body.repo_url, "requirement": body.requirement}],
        id=f"dev-pipeline-{task_id}",
        task_queue="agent-queue",
    )

    return TaskResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        repo_url=body.repo_url,
        requirement=body.requirement,
        workflow_id=handle.id,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, repo_url: str = "", requirement: str = ""):
    client = await get_temporal_client()
    workflow_id = f"dev-pipeline-{task_id}"

    try:
        handle = client.get_workflow_handle(workflow_id)
        desc = await handle.describe()
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    status_map = {
        WorkflowExecutionStatus.RUNNING: TaskStatus.WRITING,
        WorkflowExecutionStatus.COMPLETED: TaskStatus.DONE,
        WorkflowExecutionStatus.FAILED: TaskStatus.FAILED,
        WorkflowExecutionStatus.TIMED_OUT: TaskStatus.FAILED,
        WorkflowExecutionStatus.TERMINATED: TaskStatus.FAILED,
    }
    task_status = status_map.get(desc.status, TaskStatus.PENDING)

    return TaskResponse(
        task_id=task_id,
        status=task_status,
        repo_url=repo_url,
        requirement=requirement,
        workflow_id=workflow_id,
    )
