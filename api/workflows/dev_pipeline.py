"""
Temporal Workflow — DevPipelineWorkflow

Single-activity pipeline:
  run_dev_task  (agent-queue)
    └─ OpenHands does: clone → implement → self-review → commit → result.json

Crash recovery: if the agent pod dies mid-task, Temporal retries run_dev_task
on the next available agent pod. The activity runs to completion or exhausts retries.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from api.activities.agent import run_dev_task


@workflow.defn(name="DevPipelineWorkflow")
class DevPipelineWorkflow:
    @workflow.run
    async def run(self, params: dict) -> dict:
        """
        params:
          task_id     — unique ID for this task (used as workspace sub-dir)
          repo_url    — git repository to clone and modify
          requirement — natural-language description of what to implement
        """
        return await workflow.execute_activity(
            run_dev_task,
            params,
            task_queue="agent-queue",
            # Agent tasks take 5-30 min depending on complexity.
            schedule_to_close_timeout=timedelta(hours=2),
            # Heartbeat timeout: agent sends heartbeats every ~30 log lines.
            # If we don't hear from it for 5 min, something is wrong.
            heartbeat_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                initial_interval=timedelta(seconds=30),
                backoff_coefficient=2.0,
                maximum_interval=timedelta(minutes=10),
            ),
        )
