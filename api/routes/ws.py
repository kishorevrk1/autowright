"""
WebSocket endpoint — streams live workflow status updates to the Web UI.
Polls Temporal every 2 seconds and pushes JSON status events.
"""

import asyncio
import os
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from temporalio.client import Client, WorkflowExecutionStatus

router = APIRouter(tags=["websocket"])

POLL_INTERVAL = 2  # seconds

STAGE_MAP = {
    "classify_task":    "classifying",
    "run_analyst":      "analyzing",
    "run_pm":           "planning",
    "run_architect":    "architecting",
    "run_scrum_master": "writing_stories",
    "run_dev_task":     "developing",
    "run_qa_review":    "reviewing",
}


async def get_client() -> Client:
    host = os.environ.get("TEMPORAL_HOST", "localhost:7233")
    return await Client.connect(host)


@router.websocket("/ws/{task_id}")
async def task_status_ws(websocket: WebSocket, task_id: str):
    await websocket.accept()

    try:
        client = await get_client()
    except Exception as e:
        await websocket.send_json({"task_id": task_id, "error": f"Cannot connect to Temporal: {e}"})
        await websocket.close()
        return

    workflow_id = f"dev-pipeline-{task_id}"

    try:
        while True:
            try:
                handle = client.get_workflow_handle(workflow_id)
                desc = await handle.describe()

                status = desc.status
                payload = {
                    "task_id": task_id,
                    "workflow_status": status.name if status else "UNKNOWN",
                    "pending_activities": [],
                }

                # Derive human-readable stage from pending activity names
                if hasattr(desc, "pending_activities") and desc.pending_activities:
                    payload["pending_activities"] = [
                        STAGE_MAP.get(a.activity_type, a.activity_type)
                        for a in desc.pending_activities
                    ]

                if status == WorkflowExecutionStatus.COMPLETED:
                    result = await handle.result()
                    payload["result"] = result
                    await websocket.send_json(payload)
                    break

                if status in (
                    WorkflowExecutionStatus.FAILED,
                    WorkflowExecutionStatus.TIMED_OUT,
                    WorkflowExecutionStatus.TERMINATED,
                ):
                    payload["error"] = "Workflow ended with non-success status"
                    await websocket.send_json(payload)
                    break

                await websocket.send_json(payload)

            except WebSocketDisconnect:
                return  # client navigated away — clean exit, nothing to send
            except Exception as e:
                try:
                    await websocket.send_json({"task_id": task_id, "error": str(e)})
                except Exception:
                    pass  # client disconnected while we were sending the error
                return

            await asyncio.sleep(POLL_INTERVAL)

    except WebSocketDisconnect:
        pass
