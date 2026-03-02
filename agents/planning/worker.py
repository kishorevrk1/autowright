"""
Planning Worker — Temporal worker for BMAD planning phases.

Handles 5 activities on planning-queue:
  classify_task   — classify requirement as SIMPLE or COMPLEX
  run_analyst     — produce project brief
  run_pm          — produce PRD with acceptance criteria
  run_architect   — produce technical architecture document
  run_scrum_master — produce implementation stories (JSON array)

All activities are LLM-only (Ollama API calls via httpx). No code execution.
"""

import asyncio
import json
import os
from pathlib import Path

import httpx
from temporalio import activity
from temporalio.client import Client
from temporalio.worker import Worker

# ── Config ───────────────────────────────────────────────────────────────────
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
MODEL = os.getenv("PLANNING_MODEL", "qwen2.5-coder:14b")
TASK_QUEUE = "planning-queue"
PROMPTS_DIR = Path(__file__).parent / "prompts"


# ── LLM helper ───────────────────────────────────────────────────────────────

async def call_llm(system_prompt: str, user_prompt: str) -> str:
    """Call Ollama chat API and return the assistant response."""
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{OLLAMA_HOST}/api/chat",
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {"temperature": 0.2},
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


def load_prompt(name: str) -> str:
    """Load a system prompt from the prompts/ directory."""
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


# ── Activities ───────────────────────────────────────────────────────────────

@activity.defn(name="classify_task")
async def classify_task(params: dict) -> bool:
    """Classify requirement as simple (True) or complex (False)."""
    activity.heartbeat({"phase": "classifying"})
    system = load_prompt("classifier.md")
    user = f"Requirement: {params['requirement']}"
    response = await call_llm(system, user)
    activity.heartbeat({"phase": "classified"})
    return response.strip().upper().startswith("SIMPLE")


@activity.defn(name="run_analyst")
async def run_analyst(params: dict) -> str:
    """Analyze repo + requirement and produce a project brief."""
    activity.heartbeat({"phase": "analyzing"})
    system = load_prompt("analyst.md")
    user = (
        f"Repository: {params['repo_url']}\n"
        f"Requirement: {params['requirement']}"
    )
    result = await call_llm(system, user)
    activity.heartbeat({"phase": "analyzed"})
    return result


@activity.defn(name="run_pm")
async def run_pm(params: dict) -> str:
    """Produce a PRD from the analyst's brief."""
    activity.heartbeat({"phase": "planning"})
    system = load_prompt("pm.md")
    user = (
        f"Requirement: {params['requirement']}\n\n"
        f"## Analyst's Project Brief\n{params['brief']}"
    )
    result = await call_llm(system, user)
    activity.heartbeat({"phase": "planned"})
    return result


@activity.defn(name="run_architect")
async def run_architect(params: dict) -> str:
    """Produce a technical architecture document from the PRD."""
    activity.heartbeat({"phase": "architecting"})
    system = load_prompt("architect.md")
    user = (
        f"Requirement: {params['requirement']}\n\n"
        f"## Product Requirements Document\n{params['prd']}"
    )
    result = await call_llm(system, user)
    activity.heartbeat({"phase": "architected"})
    return result


@activity.defn(name="run_scrum_master")
async def run_scrum_master(params: dict) -> str:
    """Break PRD + architecture into implementation stories (JSON array)."""
    activity.heartbeat({"phase": "writing_stories"})
    system = load_prompt("scrum_master.md")
    user = (
        f"## Product Requirements Document\n{params['prd']}\n\n"
        f"## Architecture Document\n{params['architecture']}"
    )
    result = await call_llm(system, user)
    activity.heartbeat({"phase": "stories_written"})

    # Validate JSON — if the LLM wraps it in markdown, extract it
    text = result.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        json.loads(text)
    except json.JSONDecodeError:
        activity.logger.warning("Scrum master output is not valid JSON, returning raw")
    return text


# ── Worker entrypoint ────────────────────────────────────────────────────────

async def _connect_with_retry(host: str, max_attempts: int = 20) -> Client:
    """Retry connecting to Temporal until it's ready."""
    for attempt in range(1, max_attempts + 1):
        try:
            client = await Client.connect(host)
            print(f"[planning] Connected to Temporal at {host}", flush=True)
            return client
        except Exception as exc:
            wait = min(attempt * 3, 30)
            print(
                f"[planning] Temporal not ready (attempt {attempt}/{max_attempts}): {exc}",
                flush=True,
            )
            await asyncio.sleep(wait)
    raise RuntimeError(f"Could not connect to Temporal at {host} after {max_attempts} attempts")


async def main() -> None:
    client = await _connect_with_retry(TEMPORAL_HOST)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[],
        activities=[classify_task, run_analyst, run_pm, run_architect, run_scrum_master],
    )
    print(f"[planning] Listening on task queue: {TASK_QUEUE}", flush=True)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
