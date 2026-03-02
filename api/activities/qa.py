"""
Activity stub — QA review.

This exists so the workflow can reference the activity name at import time.
Real implementation runs in agents/qa/worker.py on qa-queue.
"""

from temporalio import activity


@activity.defn(name="run_qa_review")
async def run_qa_review(params: dict) -> dict:
    raise NotImplementedError("Real implementation in agents/qa/worker.py")
