# Building Autowright: A BMAD-Structured Autonomous AI Dev Platform with Temporal, OpenHands, and Local LLMs

> How we built an open-source platform where AI doesn't just write code — it plans, architects, implements, and reviews it, all orchestrated by a crash-proof workflow engine.

---

## The Problem

Every AI coding tool today works the same way: you give it a prompt, it generates code. Sometimes it's great. Often it's wrong. And when it fails halfway through a complex task, you start over.

We wanted something different:

- **AI that thinks before it codes** — structured planning, not just autocomplete
- **Crash-proof execution** — if anything fails, pick up exactly where you left off
- **Fully self-hosted** — no API costs, no code leaving your machine
- **Manager-friendly** — a non-technical person should be able to submit a requirement and get committed code back

The result is [Autowright](https://github.com/kishorevrk1/autowright): an autonomous software development platform that uses the BMAD method for structured planning, Temporal for durable orchestration, and OpenHands for code execution — all running on local LLMs via Ollama.

---

## Architecture Overview

```
Manager (Web UI)
    │
    ▼
FastAPI Orchestrator
    │
    ▼
Temporal Server (durable workflow engine)
    │
    ├── Planning Pod (LLM-only)
    │     classify → analyst → PM → architect → scrum master
    │
    ├── Developer Pod (OpenHands)
    │     clone → code → test → review → commit → push
    │
    └── QA Pod (LLM + git diff)
          review diff against PRD → APPROVED / REJECTED
```

Three pods. Three Temporal task queues. One workflow that chains them all together. Let's break down every layer and the design decisions behind it.

---

## Best Practice 1: Plan Before You Code (The BMAD Method)

Most AI coding tools take a raw requirement like "add user authentication" and immediately start writing code. This is like handing a contractor a one-sentence brief and expecting a finished building.

The [BMAD method](https://docs.bmad-method.org/) (Build More, Architect Dreams) structures AI work into phases, each with a specialized persona:

### Our 6-Phase Pipeline

| Phase | BMAD Role | What It Produces | Why It Matters |
| ----- | --------- | ---------------- | -------------- |
| 1 | Classifier | SIMPLE or COMPLEX | Avoids wasting 15 min of planning on "fix typo" tasks |
| 2 | Analyst | Project brief | Understands the codebase context before any decisions |
| 3 | Product Manager | PRD + acceptance criteria | Defines testable requirements, not vague goals |
| 4 | Architect | Technical design | Specifies which files to modify, which patterns to follow |
| 5 | Scrum Master | Implementation stories (JSON) | Breaks work into focused, ordered units |
| 6 | Developer | Code + tests + commit | Receives structured context instead of a one-liner |
| 7 | QA Engineer | APPROVED / REJECTED verdict | Reviews the diff against the PRD |

### Why This Works Better

When the Developer (OpenHands) receives a task with full planning context:

```
REQUIREMENT: Add user authentication

## PLANNING CONTEXT

### PRD
- FR-1: POST /auth/login accepts email + password, returns JWT
- FR-2: GET /auth/me returns user profile when valid token provided
- FR-3: Invalid credentials return 401 with error message

### Architecture
- Create src/routes/auth.py (follow pattern in src/routes/users.py)
- Create src/models/token.py for JWT schema
- Modify src/main.py to register auth router

### Stories
1. Create JWT utility functions (depends on: nothing)
2. Create login endpoint (depends on: JWT utils)
3. Create /auth/me endpoint (depends on: login)
4. Add tests for all auth endpoints (depends on: all above)
```

...it produces dramatically better code than when it receives just "Add user authentication."

### The Quick Flow Escape Hatch

Not every task needs a 6-phase pipeline. A classifier LLM call determines if the task is simple enough to skip planning:

```python
@activity.defn(name="classify_task")
async def classify_task(params: dict) -> bool:
    system = load_prompt("classifier.md")
    user = f"Requirement: {params['requirement']}"
    result = await call_llm(system, user)
    return result.strip().upper().startswith("SIMPLE")
```

Simple tasks like "fix the typo in README" or "add a /health endpoint" go straight to the Developer pod. Complex tasks like "implement OAuth2 with refresh tokens" get the full BMAD treatment.

**Best practice: Always provide an escape hatch for simple cases. Over-processing trivial tasks wastes time and can actually produce worse results (the LLM overthinks it).**

---

## Best Practice 2: Use Temporal for Workflow Durability

This is the single most important architectural decision in Autowright and the one feature no other open-source AI dev platform has.

### The Problem Temporal Solves

An AI coding task can take 5-30 minutes. During that time:
- The LLM might time out
- The container might run out of memory
- Docker might restart
- The network might hiccup

Without Temporal, any of these failures means starting over from scratch. With Temporal, the workflow automatically replays from the last checkpoint.

### How We Structure the Workflow

```python
@workflow.defn(name="DevPipelineWorkflow")
class DevPipelineWorkflow:
    async def run(self, params: dict) -> dict:
        # Phase 0: Classify
        is_simple = await workflow.execute_activity(
            "classify_task",
            {"requirement": requirement},
            task_queue="planning-queue",
            schedule_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        if not is_simple:
            # Phases 1-4: Planning (each is a separate activity)
            brief = await workflow.execute_activity("run_analyst", ...)
            prd = await workflow.execute_activity("run_pm", ...)
            architecture = await workflow.execute_activity("run_architect", ...)
            stories = await workflow.execute_activity("run_scrum_master", ...)

        # Phase 5: Developer (OpenHands)
        dev_result = await workflow.execute_activity(
            run_dev_task,
            {..., "brief": brief, "prd": prd, "architecture": architecture},
            schedule_to_close_timeout=timedelta(hours=2),
            heartbeat_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=3),
        )

        # Phase 6: QA Review
        qa_result = await workflow.execute_activity("run_qa_review", ...)

        return {**dev_result, "qa_verdict": qa_result["verdict"]}
```

### Key Temporal Patterns We Use

**1. Separate task queues for different pod types**

```
planning-queue  →  Lightweight pod (just httpx + Ollama calls)
agent-queue     →  Heavy pod (OpenHands + Docker socket)
qa-queue        →  Lightweight pod (httpx + git)
```

This lets you scale pods independently. Need faster planning? Add more planning pods. The agent pod is expensive (needs Docker socket, lots of RAM for OpenHands) — keep it at one replica.

**Best practice: One task queue per resource profile. Don't put lightweight LLM calls on the same queue as heavy code execution — you'll block fast activities behind slow ones.**

**2. Heartbeats for long-running activities**

OpenHands can be silent for minutes while waiting for LLM responses. Temporal's heartbeat mechanism detects stuck activities:

```python
# Time-based heartbeat — fires every 60s regardless of stdout activity
async def _heartbeat_loop():
    count = 0
    while True:
        await asyncio.sleep(60)
        count += 1
        activity.heartbeat({"heartbeat_count": count})

heartbeat_task = asyncio.create_task(_heartbeat_loop())

# Stream OpenHands output
async for raw in proc.stdout:
    print(raw.decode(), flush=True)

heartbeat_task.cancel()
```

**Best practice: Never use output-based heartbeats (e.g., "heartbeat every 30 lines of stdout"). Use time-based heartbeats. LLMs go silent for unpredictable periods — if your heartbeat depends on output, Temporal will kill the activity during a long LLM inference.**

**3. Different timeouts for different activity types**

```python
# Planning activities: fast LLM calls (30-120 seconds typically)
schedule_to_close_timeout=timedelta(minutes=10)
heartbeat_timeout=timedelta(minutes=3)

# Developer activity: full OpenHands run (5-30 minutes)
schedule_to_close_timeout=timedelta(hours=2)
heartbeat_timeout=timedelta(minutes=5)

# QA review: moderate LLM call with diff context
schedule_to_close_timeout=timedelta(minutes=30)
heartbeat_timeout=timedelta(minutes=3)
```

**Best practice: Set heartbeat_timeout to at least 2x your expected maximum LLM inference time. For local models on consumer hardware, a single inference can take 2-3 minutes.**

**4. Retry policies tuned per activity**

```python
# Planning: cheap to retry (just an LLM call), fail fast
RetryPolicy(maximum_attempts=2, initial_interval=timedelta(seconds=10))

# Developer: expensive to retry (full clone + OpenHands run), be patient
RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=30),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=10),
)
```

**Best practice: Retry policies should reflect the cost of retrying. Cheap activities (LLM calls) get low max_attempts with short intervals. Expensive activities (code execution) get more attempts with longer backoff.**

---

## Best Practice 3: Separate Planning from Execution

Our planning pod is deliberately simple — no OpenHands, no Docker, no code execution. It's just a Python process that calls Ollama's API:

```python
async def call_llm(system_prompt: str, user_prompt: str) -> str:
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
        return resp.json()["message"]["content"]
```

### Why Not Use OpenHands for Everything?

OpenHands is powerful but heavy:
- Spawns sandbox containers (needs Docker socket)
- Has complex state management (agent loops, observations, actions)
- Designed for code execution, not document generation

Planning activities don't execute code. They're pure `text in → text out` LLM calls. Using OpenHands for them would be like driving a truck to the corner store.

**Dockerfile comparison:**

```dockerfile
# Planning pod: 150 MB image
FROM python:3.12-slim
RUN pip install temporalio httpx

# Agent pod: 3+ GB image
FROM python:3.12-slim
RUN pip install openhands temporalio docker
RUN apt-get install -y git docker-cli
```

**Best practice: Use the simplest tool that gets the job done. If an activity is just an LLM API call, don't wrap it in a full agent framework. Save the heavy machinery for activities that need it.**

---

## Best Practice 4: Structured Prompts with Clear Output Contracts

Each BMAD role has a system prompt that specifies exact output format:

### Analyst Prompt (Produces Markdown)

```markdown
You are a Senior Business & Technical Analyst.

## Your Output: Project Brief

Produce a markdown document with these sections:

### 1. Requirement Summary
### 2. Scope Assessment
### 3. Key Risks & Dependencies
### 4. Assumptions
### 5. Success Criteria

Rules:
- Be concise — under 500 words
- Don't write code or suggest implementations
```

### Scrum Master Prompt (Produces JSON)

```markdown
You are a Scrum Master.

## Your Output: Stories JSON Array

Produce a JSON array of story objects:
[
  {
    "title": "Short descriptive title",
    "description": "What to implement",
    "acceptance_criteria": ["Testable criterion 1"],
    "files_affected": ["src/routes/auth.py"],
    "depends_on": []
  }
]

Rules:
- Output ONLY the JSON array
- Each story: 1-3 files maximum
- Include a testing story for each implementation story
```

### Handling Non-Compliant Output

LLMs don't always follow instructions perfectly. We handle this gracefully:

```python
# Strip markdown code fences if the LLM wraps JSON in ```
text = result.strip()
if text.startswith("```"):
    lines = text.split("\n")
    lines = [l for l in lines if not l.strip().startswith("```")]
    text = "\n".join(lines)

try:
    json.loads(text)
except json.JSONDecodeError:
    activity.logger.warning("Output is not valid JSON, returning raw")
```

**Best practice: Define explicit output contracts in your prompts, but always handle the case where the LLM doesn't comply. Fail gracefully — pass the raw output downstream rather than crashing the pipeline.**

---

## Best Practice 5: Self-Hosted LLMs with Ollama

We chose Ollama for several reasons:

1. **Zero API costs** — local inference, unlimited usage
2. **No code exfiltration** — your code never leaves your machine
3. **Model flexibility** — swap models via environment variable
4. **Simple API** — OpenAI-compatible `/api/chat` endpoint

### Model Configuration Strategy

Different pods can use different models:

```yaml
# docker-compose.yaml
planning:
  environment:
    - PLANNING_MODEL=qwen2.5-coder:14b    # Fast, good at structured output

agent:
  environment:
    - MODEL=ollama/qwen2.5-coder:14b       # Needs tool calling for OpenHands

qa:
  environment:
    - QA_MODEL=qwen2.5-coder:14b           # Good at code review
```

In production (K8s), you might use a larger model:

```yaml
# k8s/agents/planning.yaml
env:
  - name: PLANNING_MODEL
    value: "qwen3-coder:30b"    # More capable, K8s pod has more RAM
```

**Best practice: Make models configurable per pod via environment variables. Planning needs strong reasoning. Coding needs strong tool-calling. Review needs strong code comprehension. These might be different models.**

### Temperature Settings

```python
# Planning activities: slightly creative (exploring design space)
"options": {"temperature": 0.2}

# Developer (OpenHands): deterministic (executing a plan)
temperature = 0.1

# QA review: deterministic (evaluating correctness)
"options": {"temperature": 0.1}
```

**Best practice: Lower temperature for execution, slightly higher for planning. You want creative architectural thinking but deterministic code output.**

---

## Best Practice 6: Real-Time Pipeline Visibility

The Web UI shows a step-by-step pipeline stepper, not just a binary "running/done":

```
[Classify ✓] → [Analyze ✓] → [Plan ✓] → [Architect ●] → [Stories ○] → [Develop ○] → [Review ○]
```

This is powered by Temporal's `pending_activities` field, streamed via WebSocket:

```python
# API WebSocket handler
STAGE_MAP = {
    "classify_task":    "classifying",
    "run_analyst":      "analyzing",
    "run_pm":           "planning",
    "run_architect":    "architecting",
    "run_scrum_master": "writing_stories",
    "run_dev_task":     "developing",
    "run_qa_review":    "reviewing",
}

# In the polling loop:
if desc.pending_activities:
    payload["pending_activities"] = [
        STAGE_MAP.get(a.activity_type, a.activity_type)
        for a in desc.pending_activities
    ]
```

The React component tracks stage transitions:

```tsx
// When the current stage changes, mark the previous one as completed
if (prevStageRef.current && prevStageRef.current !== stage) {
  setCompletedStages((prev) => new Set([...prev, prevStageRef.current!]));
}
```

**Best practice: Expose workflow internals to the UI. Temporal already tracks activity state — pipe it through. Users need to know if the AI is planning, coding, or reviewing. "Running..." for 20 minutes is a terrible experience.**

---

## Best Practice 7: QA as a Pipeline Gate

The QA pod reviews the developer's git diff against the PRD:

```python
def get_git_diff(task_id: str) -> str:
    repo_dir = os.path.join(WORKSPACE_BASE, task_id, "repo")
    result = subprocess.run(
        ["git", "diff", "HEAD~1", "HEAD"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    return result.stdout
```

The QA prompt checks:
1. Does the diff implement all functional requirements?
2. Are there obvious bugs or security issues?
3. Are tests present?
4. Does the code follow existing patterns?

The verdict is structured JSON:

```json
{
  "verdict": "APPROVED",
  "summary": "All acceptance criteria met. JWT implementation follows existing patterns.",
  "issues": [],
  "missing_requirements": [],
  "suggestions": ["Consider adding rate limiting to the login endpoint"]
}
```

**Best practice: Separate the reviewer from the coder. Self-review catches some issues, but having a different LLM context (without the "sunk cost" of having written the code) catches more. The QA pod sees only the diff and the requirements — no emotional attachment to the implementation.**

---

## Docker Compose: The Full Stack

```yaml
services:
  postgres:           # Temporal's persistence
  temporal:           # Workflow engine
  temporal-ui:        # Temporal dashboard
  api:                # FastAPI orchestrator
  planning:           # BMAD planning pod (LLM-only)
  agent:              # OpenHands developer pod
  qa:                 # QA review pod

volumes:
  workspace:          # Shared: agent writes, QA reads
```

One command to start everything:

```bash
docker compose up
```

The planning pod has no volume mounts (pure LLM calls). The QA pod shares the `workspace` volume with the agent pod so it can read git diffs. The agent pod also mounts the Docker socket for OpenHands sandbox containers.

**Best practice: Share state through volumes, not APIs. The QA pod reading a git diff from the filesystem is simpler and more reliable than the agent pod exposing the diff via an HTTP endpoint.**

---

## Lessons Learned

### 1. Local LLMs Have Limits

Our 14B model (`qwen2.5-coder:14b`) handles planning and review well but struggles with complex multi-file implementations via OpenHands. The 30B model is better but needs 22 GiB RAM. For serious production use, consider a cloud LLM for the developer activity while keeping planning/QA on local models.

### 2. Heartbeats Are Critical

We lost hours debugging "CancelledError" crashes before realizing our line-count-based heartbeats weren't firing during long LLM inference pauses. Time-based heartbeats (every 60s via `asyncio.create_task`) solved it immediately.

### 3. Quick Flow Matters

Early versions ran the full 6-phase pipeline for every task. A "fix typo in README" would generate a project brief, PRD, architecture document, and stories before making a one-line change. The classifier saves 15+ minutes on simple tasks.

### 4. Temporal Is the Right Abstraction

We considered Redis queues, Celery, and custom orchestration. Temporal's replay semantics, heartbeat monitoring, and retry policies eliminated entire categories of bugs. The learning curve is worth it for any multi-step AI pipeline.

---

## Getting Started

```bash
# Prerequisites: Docker Desktop + Ollama + Node.js 18+
ollama pull qwen2.5-coder:14b

# Start the platform
git clone https://github.com/kishorevrk1/autowright
cd autowright
docker compose up

# Start the Web UI
cd web && npm install && npm run dev
```

Open http://localhost:3000, paste a repo URL, type a requirement, and watch the pipeline work.

---

## What's Next

- **Deploy phase**: Add a deployer pod that builds Docker images and writes K8s manifests
- **Multi-model routing**: Use a strong reasoning model for planning and a fast coding model for implementation
- **Feedback loop**: If QA rejects, automatically send feedback back to the developer for a second pass
- **Artifact storage**: Persist BMAD artifacts (PRDs, architecture docs) for audit trail and learning

---

*Autowright is open source under MIT. Star it on [GitHub](https://github.com/kishorevrk1/autowright) if you find it useful.*
