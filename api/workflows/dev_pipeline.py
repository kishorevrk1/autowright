"""
Temporal Workflow — DevPipelineWorkflow (API-side reference copy)

6-phase BMAD pipeline:
  1. classify_task     (planning-queue) → SIMPLE or COMPLEX
  2. run_analyst       (planning-queue) → project brief
  3. run_pm            (planning-queue) → PRD
  4. run_architect     (planning-queue) → architecture doc
  5. run_scrum_master  (planning-queue) → implementation stories
  6. run_dev_task      (agent-queue)    → OpenHands: code + test + commit
  7. run_qa_review     (qa-queue)       → verdict: APPROVED / REJECTED

Quick flow: if classify_task returns SIMPLE, phases 2-5 are skipped.

NOTE: The authoritative workflow definition lives in agents/agent/worker.py.
      This file is a reference copy used for IDE imports in the API process.
"""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from api.activities.agent import run_dev_task
    from api.activities.planning import (
        classify_task,
        run_analyst,
        run_architect,
        run_pm,
        run_scrum_master,
    )
    from api.activities.qa import run_qa_review


_PLANNING_RETRY = RetryPolicy(maximum_attempts=2, initial_interval=timedelta(seconds=10))
_DEV_RETRY = RetryPolicy(maximum_attempts=3, initial_interval=timedelta(seconds=30))
_QA_RETRY = RetryPolicy(maximum_attempts=2, initial_interval=timedelta(seconds=10))


@workflow.defn(name="DevPipelineWorkflow")
class DevPipelineWorkflow:
    @workflow.run
    async def run(self, params: dict) -> dict:
        task_id = params["task_id"]
        repo_url = params["repo_url"]
        requirement = params["requirement"]

        is_simple = await workflow.execute_activity(
            classify_task, {"requirement": requirement},
            task_queue="planning-queue",
            schedule_to_close_timeout=timedelta(minutes=5),
            heartbeat_timeout=timedelta(minutes=3),
            retry_policy=_PLANNING_RETRY,
        )

        brief = prd = architecture = stories = ""

        if not is_simple:
            brief = await workflow.execute_activity(
                run_analyst, {"repo_url": repo_url, "requirement": requirement},
                task_queue="planning-queue",
                schedule_to_close_timeout=timedelta(minutes=10),
                heartbeat_timeout=timedelta(minutes=3),
                retry_policy=_PLANNING_RETRY,
            )
            prd = await workflow.execute_activity(
                run_pm, {"requirement": requirement, "brief": brief},
                task_queue="planning-queue",
                schedule_to_close_timeout=timedelta(minutes=10),
                heartbeat_timeout=timedelta(minutes=3),
                retry_policy=_PLANNING_RETRY,
            )
            architecture = await workflow.execute_activity(
                run_architect, {"requirement": requirement, "prd": prd},
                task_queue="planning-queue",
                schedule_to_close_timeout=timedelta(minutes=10),
                heartbeat_timeout=timedelta(minutes=3),
                retry_policy=_PLANNING_RETRY,
            )
            stories = await workflow.execute_activity(
                run_scrum_master, {"prd": prd, "architecture": architecture},
                task_queue="planning-queue",
                schedule_to_close_timeout=timedelta(minutes=10),
                heartbeat_timeout=timedelta(minutes=3),
                retry_policy=_PLANNING_RETRY,
            )

        dev_result = await workflow.execute_activity(
            run_dev_task,
            {"task_id": task_id, "repo_url": repo_url, "requirement": requirement,
             "brief": brief, "prd": prd, "architecture": architecture, "stories": stories},
            task_queue="agent-queue",
            schedule_to_close_timeout=timedelta(hours=2),
            heartbeat_timeout=timedelta(minutes=5),
            retry_policy=_DEV_RETRY,
        )

        qa_result = await workflow.execute_activity(
            run_qa_review,
            {"task_id": task_id, "dev_result": dev_result, "prd": prd, "stories": stories},
            task_queue="qa-queue",
            schedule_to_close_timeout=timedelta(minutes=30),
            heartbeat_timeout=timedelta(minutes=3),
            retry_policy=_QA_RETRY,
        )

        return {**dev_result, "qa_verdict": qa_result.get("verdict"), "planning_used": not is_simple}
