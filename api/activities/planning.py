"""
Activity stubs — BMAD planning phases.

These exist so the workflow can reference activity names at import time.
Real implementations run in agents/planning/worker.py on planning-queue.
"""

from temporalio import activity


@activity.defn(name="classify_task")
async def classify_task(params: dict) -> bool:
    raise NotImplementedError("Real implementation in agents/planning/worker.py")


@activity.defn(name="run_analyst")
async def run_analyst(params: dict) -> str:
    raise NotImplementedError("Real implementation in agents/planning/worker.py")


@activity.defn(name="run_pm")
async def run_pm(params: dict) -> str:
    raise NotImplementedError("Real implementation in agents/planning/worker.py")


@activity.defn(name="run_architect")
async def run_architect(params: dict) -> str:
    raise NotImplementedError("Real implementation in agents/planning/worker.py")


@activity.defn(name="run_scrum_master")
async def run_scrum_master(params: dict) -> str:
    raise NotImplementedError("Real implementation in agents/planning/worker.py")
