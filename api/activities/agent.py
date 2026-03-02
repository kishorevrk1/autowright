"""
Activity stub — run_dev_task.

This file exists so the workflow can import the activity name at load time.
The real implementation runs in agents/agent/worker.py on the agent pod,
listening on task queue "agent-queue".
"""

from temporalio import activity


@activity.defn(name="run_dev_task")
async def run_dev_task(params: dict) -> dict:
    raise NotImplementedError(
        "Real implementation lives in agents/agent/worker.py "
        "(Temporal worker on agent-queue)"
    )
