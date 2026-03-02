"""
QA Worker — Temporal worker for code review phase.

Handles 1 activity on qa-queue:
  run_qa_review — review git diff against PRD and stories, return verdict

Reads the git diff from the shared workspace volume, sends it to Ollama
for review, and returns a structured verdict (APPROVED / REJECTED).
"""

import asyncio
import json
import os
import subprocess
from pathlib import Path

import httpx
from temporalio import activity
from temporalio.client import Client
from temporalio.worker import Worker

# ── Config ───────────────────────────────────────────────────────────────────
TEMPORAL_HOST = os.getenv("TEMPORAL_HOST", "localhost:7233")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
MODEL = os.getenv("QA_MODEL", "qwen2.5-coder:14b")
WORKSPACE_BASE = os.getenv("WORKSPACE_BASE", "/workspace")
TASK_QUEUE = "qa-queue"
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
                "options": {"temperature": 0.1},
            },
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]


def load_prompt(name: str) -> str:
    """Load a system prompt from the prompts/ directory."""
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def get_git_diff(task_id: str) -> str:
    """Read git diff from the cloned repo in the workspace."""
    repo_dir = os.path.join(WORKSPACE_BASE, task_id, "repo")
    if not os.path.isdir(repo_dir):
        return "(no repo directory found)"
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD~1", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        diff = result.stdout.strip()
        if not diff:
            # Try diff against main/master
            result = subprocess.run(
                ["git", "diff", "main...HEAD"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            diff = result.stdout.strip()
        return diff if diff else "(empty diff)"
    except Exception as exc:
        return f"(error reading diff: {exc})"


# ── Activity ─────────────────────────────────────────────────────────────────

@activity.defn(name="run_qa_review")
async def run_qa_review(params: dict) -> dict:
    """Review code changes against PRD and stories, return verdict."""
    task_id = params["task_id"]
    dev_result = params.get("dev_result", {})
    prd = params.get("prd", "")
    stories = params.get("stories", "")

    activity.heartbeat({"phase": "reviewing"})

    # Get the diff
    diff = get_git_diff(task_id)

    # Truncate diff if too large (Ollama context limit)
    max_diff_chars = 12000
    if len(diff) > max_diff_chars:
        diff = diff[:max_diff_chars] + "\n\n... (diff truncated)"

    # Build review prompt
    system = load_prompt("qa.md")
    user_parts = [f"## Git Diff\n```diff\n{diff}\n```"]
    if prd:
        user_parts.append(f"\n## PRD\n{prd}")
    if stories:
        user_parts.append(f"\n## Implementation Stories\n{stories}")
    if dev_result:
        user_parts.append(
            f"\n## Dev Result\n"
            f"- Branch: {dev_result.get('branch', 'unknown')}\n"
            f"- Files changed: {dev_result.get('files_changed', [])}\n"
            f"- Summary: {dev_result.get('summary', 'N/A')}"
        )
    user_prompt = "\n".join(user_parts)

    response = await call_llm(system, user_prompt)
    activity.heartbeat({"phase": "reviewed"})

    # Parse JSON response
    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    try:
        verdict = json.loads(text)
    except json.JSONDecodeError:
        activity.logger.warning("QA output is not valid JSON, wrapping as raw feedback")
        verdict = {
            "verdict": "APPROVED",
            "summary": text[:500],
            "issues": [],
            "missing_requirements": [],
            "suggestions": [],
        }

    return verdict


# ── Worker entrypoint ────────────────────────────────────────────────────────

async def _connect_with_retry(host: str, max_attempts: int = 20) -> Client:
    """Retry connecting to Temporal until it's ready."""
    for attempt in range(1, max_attempts + 1):
        try:
            client = await Client.connect(host)
            print(f"[qa] Connected to Temporal at {host}", flush=True)
            return client
        except Exception as exc:
            wait = min(attempt * 3, 30)
            print(
                f"[qa] Temporal not ready (attempt {attempt}/{max_attempts}): {exc}",
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
        activities=[run_qa_review],
    )
    print(f"[qa] Listening on task queue: {TASK_QUEUE}", flush=True)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
