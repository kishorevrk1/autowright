"""
Autowright Agent Worker — Temporal workflow + OpenHands activity.

Hosts the DevPipelineWorkflow (6-phase BMAD pipeline) and the
run_dev_task activity (OpenHands CodeActAgent).

The workflow chains activities across 3 task queues:
  planning-queue  →  classify, analyst, PM, architect, scrum master
  agent-queue     →  run_dev_task (OpenHands: code → test → commit)
  qa-queue        →  run_qa_review (LLM review of diff vs PRD)

Registered on task queue: agent-queue
Workflow:                 DevPipelineWorkflow
Activity:                 run_dev_task
"""

import asyncio
import io
import json
import os
import tarfile
import textwrap
from datetime import timedelta

from temporalio import activity, workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy
from temporalio.worker import Worker

# ── Config from environment ───────────────────────────────────────────────────
TEMPORAL_HOST  = os.getenv("TEMPORAL_HOST", "localhost:7233")
OLLAMA_HOST    = os.getenv("OLLAMA_HOST", "http://host.docker.internal:11434")
MODEL          = os.getenv("MODEL", "ollama/qwen2.5-coder:14b")
WORKSPACE_BASE = os.getenv("WORKSPACE_BASE", "/workspace")
RUNTIME_TYPE   = os.getenv("RUNTIME_TYPE", "docker")   # docker | local
DOCKER_HOST    = os.getenv("DOCKER_HOST_ADDR", "host.docker.internal")
CONFIG_FILE    = "/app/config.toml"
TASK_QUEUE     = "agent-queue"


# ── OpenHands config ──────────────────────────────────────────────────────────

def _write_config(workspace: str) -> None:
    """Write /app/config.toml for OpenHands."""
    if RUNTIME_TYPE == "local":
        sandbox_section = textwrap.dedent("""\
            [sandbox]
            # local runtime: action server runs as subprocess in same pod.
            # No Docker socket needed — works cleanly in Kubernetes.
            runtime_type = "local"
            local_runtime_url = "http://localhost"
        """)
    else:
        sandbox_section = textwrap.dedent(f"""\
            [sandbox]
            # docker runtime: action server runs in a sibling container.
            # Requires /var/run/docker.sock mounted.
            local_runtime_url = "http://{DOCKER_HOST}"
        """)

    config = textwrap.dedent(f"""\
        [core]
        run_as_openhands = false

        {sandbox_section}
        [llm]
        model = "{MODEL}"
        base_url = "{OLLAMA_HOST}"
        api_key = "ollama"
        temperature = 0.1
        num_retries = 5
        retry_min_wait = 10
        retry_max_wait = 60
    """)
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        f.write(config)


# ── Task prompt builder ───────────────────────────────────────────────────────

def _build_task(
    repo_url: str, requirement: str, task_id: str, workspace: str,
    brief: str = "", prd: str = "", architecture: str = "", stories: str = "",
) -> str:
    """
    Build the full pipeline task prompt for OpenHands.
    The agent clones, implements, self-reviews, commits, and writes result.json.
    When planning artifacts are provided, they're injected as structured context.
    """
    branch      = f"feature/{task_id[:12]}"
    repo_dir    = f"{workspace}/repo"
    result_path = f"{workspace}/result.json"

    # Build planning context section if BMAD phases produced artifacts
    context_section = ""
    if prd:
        context_section = textwrap.dedent(f"""\
            ## PLANNING CONTEXT (from BMAD pipeline)

            ### Project Brief
            {brief}

            ### Product Requirements Document (PRD)
            {prd}

            ### Technical Architecture
            {architecture}

            ### Implementation Stories
            {stories}

            Follow the architecture document. Implement the stories in order.
            Ensure all acceptance criteria from the PRD are met.

        """)

    return textwrap.dedent(f"""\
        You are an autonomous software developer. Complete all steps below without asking.

        REPOSITORY : {repo_url}
        REQUIREMENT: {requirement}
        BRANCH     : {branch}

        {context_section}## STEP 1 — CLONE & BRANCH
        ```bash
        git clone {repo_url} {repo_dir}
        cd {repo_dir}
        git checkout -b {branch}
        ```

        ## STEP 2 — EXPLORE
        Read the relevant source files to understand the codebase before writing code.

        ## STEP 3 — IMPLEMENT
        Implement "{requirement}".
        Follow the existing code style. Make minimal, focused changes only.

        ## STEP 4 — TEST
        Run the test suite:
        ```bash
        cd {repo_dir}
        python -m pytest --tb=short -q 2>/dev/null || echo "no tests"
        ```
        Fix any failures your changes cause.

        ## STEP 5 — SELF-REVIEW
        ```bash
        cd {repo_dir} && git diff HEAD
        ```
        Check for logic errors, missing error handling, security issues.
        Fix anything you find before committing.

        ## STEP 6 — COMMIT
        ```bash
        cd {repo_dir}
        git add -A
        git config user.email "agent@autowright.dev"
        git config user.name "Autowright Agent"
        git commit -m "feat: {requirement[:60].rstrip()}"
        ```

        ## STEP 7 — WRITE RESULT
        Get the commit SHA and write {result_path}:
        ```bash
        cd {repo_dir} && git rev-parse HEAD
        ```
        Then write the file with content:
        {{
          "status": "done",
          "task_id": "{task_id}",
          "branch": "{branch}",
          "commit_sha": "<actual SHA from git rev-parse HEAD>",
          "files_changed": ["<list each file you modified>"],
          "summary": "<1-2 sentences describing what was implemented>"
        }}

        When result.json is written and the code is committed, call finish.
    """)


# ── Workspace copy (Docker runtime only) ──────────────────────────────────────

def _copy_sandbox_workspace(task_workspace: str) -> None:
    """
    Copy files from the OpenHands sandbox container into our workspace mount.

    With Docker runtime the sandbox runs as a sibling container. OpenHands tells
    the Docker daemon to bind-mount WORKSPACE_BASE from the daemon's perspective,
    which differs from our agent container's named-volume mount. We bridge that
    gap by extracting the sandbox's /workspace via docker cp after each run.

    With local runtime (K8s) OpenHands writes directly to the shared filesystem,
    so no copy is needed.
    """
    if RUNTIME_TYPE != "docker":
        return
    try:
        import docker as docker_sdk
        client = docker_sdk.from_env()
        containers = client.containers.list(
            all=True, filters={"name": "openhands-runtime"}
        )
        if not containers:
            print("[worker] No openhands-runtime container found — skipping copy", flush=True)
            return
        # Most-recently-created sandbox first
        containers.sort(key=lambda c: c.attrs.get("Created", ""), reverse=True)
        sandbox = containers[0]
        print(f"[worker] Copying /workspace from sandbox {sandbox.name}", flush=True)
        bits, _ = sandbox.get_archive("/workspace")
        buf = io.BytesIO(b"".join(bits))
        with tarfile.open(fileobj=buf) as tar:
            for member in tar.getmembers():
                name = member.name
                if name.startswith("workspace/"):
                    name = name[len("workspace/"):]
                elif name == "workspace":
                    continue
                if not name:
                    continue
                member.name = name
                tar.extract(member, path=task_workspace, set_attrs=False)
        print(f"[worker] Workspace copy done → {task_workspace}", flush=True)
    except Exception as exc:
        print(f"[worker] Warning: workspace copy failed: {exc}", flush=True)


# ── Temporal activity ─────────────────────────────────────────────────────────

@activity.defn(name="run_dev_task")
async def run_dev_task(params: dict) -> dict:
    """
    Full pipeline activity: clone → implement → review → commit → report.

    Sends heartbeats every ~30 log lines so Temporal knows we're alive
    during the long OpenHands run (can take 5-15 min per task).
    """
    task_id      = params["task_id"]
    repo_url     = params["repo_url"]
    requirement  = params["requirement"]
    brief        = params.get("brief", "")
    prd          = params.get("prd", "")
    architecture = params.get("architecture", "")
    stories      = params.get("stories", "")

    workspace = os.path.join(WORKSPACE_BASE, task_id)
    os.makedirs(workspace, exist_ok=True)

    _write_config(workspace)

    task = _build_task(
        repo_url, requirement, task_id, workspace,
        brief=brief, prd=prd, architecture=architecture, stories=stories,
    )
    activity.logger.info(f"[{task_id}] Starting OpenHands | model={MODEL}")

    env = {
        **os.environ,
        "WORKSPACE_BASE":        workspace,
        "OPENHANDS_CONFIG_FILE": CONFIG_FILE,
        "LLM_MODEL":             MODEL,
        "LLM_BASE_URL":          OLLAMA_HOST,
        "LLM_API_KEY":           "ollama",
        "DOCKER_HOST_ADDR":      DOCKER_HOST,
        "PYTHONUNBUFFERED":      "1",
    }

    proc = await asyncio.create_subprocess_exec(
        "python", "-m", "openhands.core.main",
        "-t", task,
        "-d", workspace,
        "-c", "CodeActAgent",
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    # Time-based heartbeat task: OpenHands can be silent for several minutes
    # while waiting for an LLM response, so line-count heartbeats aren't reliable.
    # This background task fires every 60s regardless of stdout activity.
    async def _heartbeat_loop() -> None:
        count = 0
        while True:
            await asyncio.sleep(60)
            count += 1
            activity.heartbeat({"heartbeat_count": count})

    heartbeat_task = asyncio.create_task(_heartbeat_loop())

    line_count = 0
    async for raw in proc.stdout:
        line = raw.decode(errors="replace").rstrip()
        print(line, flush=True)
        line_count += 1

    heartbeat_task.cancel()
    try:
        await heartbeat_task
    except asyncio.CancelledError:
        pass

    await proc.wait()
    activity.logger.info(f"[{task_id}] OpenHands exit code: {proc.returncode}")

    # Docker runtime: copy files from sandbox container into our volume mount
    _copy_sandbox_workspace(workspace)

    # Read result.json written by the agent
    result_path = os.path.join(workspace, "result.json")
    if os.path.exists(result_path):
        with open(result_path) as f:
            return json.load(f)

    # Fallback if agent didn't write result.json
    return {
        "status":    "done" if proc.returncode == 0 else "error",
        "task_id":   task_id,
        "exit_code": proc.returncode,
    }


# ── Retry policies ───────────────────────────────────────────────────────────

_PLANNING_RETRY = RetryPolicy(
    maximum_attempts=2,
    initial_interval=timedelta(seconds=10),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
)

_DEV_RETRY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=30),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=10),
)

_QA_RETRY = RetryPolicy(
    maximum_attempts=2,
    initial_interval=timedelta(seconds=10),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=5),
)


# ── Temporal workflow — 6-phase BMAD pipeline ────────────────────────────────

@workflow.defn(name="DevPipelineWorkflow")
class DevPipelineWorkflow:
    """
    BMAD-structured pipeline:
      1. classify_task     → SIMPLE or COMPLEX
      2. run_analyst       → project brief        (skipped if SIMPLE)
      3. run_pm            → PRD                   (skipped if SIMPLE)
      4. run_architect     → architecture doc      (skipped if SIMPLE)
      5. run_scrum_master  → implementation stories(skipped if SIMPLE)
      6. run_dev_task      → OpenHands CodeActAgent
      7. run_qa_review     → verdict (APPROVED/REJECTED)

    Activities 1-5 run on planning-queue (LLM-only pods).
    Activity 6 runs on agent-queue (OpenHands pod).
    Activity 7 runs on qa-queue (LLM + git diff reading).
    """

    @workflow.run
    async def run(self, params: dict) -> dict:
        task_id     = params["task_id"]
        repo_url    = params["repo_url"]
        requirement = params["requirement"]

        # ── Phase 0: Classify ────────────────────────────────────────
        is_simple = await workflow.execute_activity(
            "classify_task",
            {"requirement": requirement},
            task_queue="planning-queue",
            schedule_to_close_timeout=timedelta(minutes=5),
            heartbeat_timeout=timedelta(minutes=3),
            retry_policy=_PLANNING_RETRY,
        )

        brief = ""
        prd = ""
        architecture = ""
        stories = ""

        if not is_simple:
            # ── Phase 1: Analyst ─────────────────────────────────────
            brief = await workflow.execute_activity(
                "run_analyst",
                {"repo_url": repo_url, "requirement": requirement},
                task_queue="planning-queue",
                schedule_to_close_timeout=timedelta(minutes=10),
                heartbeat_timeout=timedelta(minutes=3),
                retry_policy=_PLANNING_RETRY,
            )

            # ── Phase 2: Product Manager ─────────────────────────────
            prd = await workflow.execute_activity(
                "run_pm",
                {"requirement": requirement, "brief": brief},
                task_queue="planning-queue",
                schedule_to_close_timeout=timedelta(minutes=10),
                heartbeat_timeout=timedelta(minutes=3),
                retry_policy=_PLANNING_RETRY,
            )

            # ── Phase 3: Architect ───────────────────────────────────
            architecture = await workflow.execute_activity(
                "run_architect",
                {"requirement": requirement, "prd": prd},
                task_queue="planning-queue",
                schedule_to_close_timeout=timedelta(minutes=10),
                heartbeat_timeout=timedelta(minutes=3),
                retry_policy=_PLANNING_RETRY,
            )

            # ── Phase 4: Scrum Master ────────────────────────────────
            stories = await workflow.execute_activity(
                "run_scrum_master",
                {"prd": prd, "architecture": architecture},
                task_queue="planning-queue",
                schedule_to_close_timeout=timedelta(minutes=10),
                heartbeat_timeout=timedelta(minutes=3),
                retry_policy=_PLANNING_RETRY,
            )

        # ── Phase 5: Developer (OpenHands) ───────────────────────────
        dev_result = await workflow.execute_activity(
            run_dev_task,
            {
                "task_id": task_id,
                "repo_url": repo_url,
                "requirement": requirement,
                "brief": brief,
                "prd": prd,
                "architecture": architecture,
                "stories": stories,
            },
            schedule_to_close_timeout=timedelta(hours=2),
            heartbeat_timeout=timedelta(minutes=5),
            retry_policy=_DEV_RETRY,
        )

        # ── Phase 6: QA Review ───────────────────────────────────────
        qa_result = await workflow.execute_activity(
            "run_qa_review",
            {
                "task_id": task_id,
                "dev_result": dev_result,
                "prd": prd,
                "stories": stories,
            },
            task_queue="qa-queue",
            schedule_to_close_timeout=timedelta(minutes=30),
            heartbeat_timeout=timedelta(minutes=3),
            retry_policy=_QA_RETRY,
        )

        return {
            **dev_result,
            "qa_verdict": qa_result.get("verdict", "UNKNOWN"),
            "qa_feedback": qa_result.get("summary", ""),
            "planning_used": not is_simple,
        }


# ── Worker entrypoint ─────────────────────────────────────────────────────────

async def _connect_with_retry(host: str, max_attempts: int = 20) -> Client:
    """Retry connecting to Temporal until it's ready (auto-setup takes ~10-30s)."""
    for attempt in range(1, max_attempts + 1):
        try:
            client = await Client.connect(host)
            print(f"[worker] Connected to Temporal at {host}", flush=True)
            return client
        except Exception as exc:
            wait = min(attempt * 3, 30)
            print(f"[worker] Temporal not ready (attempt {attempt}/{max_attempts}): {exc}", flush=True)
            print(f"[worker] Retrying in {wait}s...", flush=True)
            await asyncio.sleep(wait)
    raise RuntimeError(f"Could not connect to Temporal at {host} after {max_attempts} attempts")


async def main() -> None:
    client = await _connect_with_retry(TEMPORAL_HOST)
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[DevPipelineWorkflow],
        activities=[run_dev_task],
    )
    print(f"[worker] Listening on task queue: {TASK_QUEUE}", flush=True)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
