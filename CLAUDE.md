# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Autowright is an autonomous AI software development platform using the BMAD method (Build More, Architect Dreams). A human manager sends requirements via a Web UI, and a 6-phase AI pipeline — powered by Temporal, Ollama, and OpenHands — analyzes, plans, architects, codes, and reviews the changes autonomously.

**Pipeline:** Manager chat → FastAPI → Temporal Workflow → Planning pods (BMAD phases) → Developer pod (OpenHands) → QA pod → committed code

## Commands

### Local dev (no Minikube needed)
```bash
# Start Temporal + API + Planning + Agent + QA
docker compose up

# Start Web UI
cd web && npm install && npm run dev
```

### Kubernetes (Minikube)
```bash
# One-time setup
./scripts/setup-minikube.sh
./scripts/create-git-secret.sh ~/.ssh/id_rsa

# Build all Docker images into Minikube
./scripts/build-images.sh

# Deploy everything
./scripts/deploy-all.sh

# Port-forward services for local access
kubectl port-forward svc/temporal-ui 8080:8080 -n autowright
kubectl port-forward svc/orchestrator-api 8000:8000 -n autowright
```

### Submit a task (test end-to-end)
```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/you/repo", "requirement": "Add a /health endpoint"}'
```

## Architecture

```
web/          Next.js 15 UI  (ChatInput, TaskFeed with pipeline stepper, PodStatus)
api/          FastAPI orchestrator
  main.py         — app entrypoint, CORS
  routes/tasks.py — POST /tasks starts Temporal workflow on agent-queue
  routes/ws.py    — WebSocket /ws/{task_id} streams pipeline stage updates
  activities/     — activity stubs (planning.py, qa.py, agent.py — for IDE import only)
  workflows/      — workflow stub (reference copy of DevPipelineWorkflow)
agents/
  planning/       — BMAD planning pod (LLM-only, no code execution)
    worker.py     — 5 activities: classify, analyst, PM, architect, scrum master
    prompts/      — system prompts for each BMAD role
    Dockerfile    — Python 3.12 + temporalio + httpx
  agent/          — Developer pod (OpenHands CodeActAgent)
    worker.py     — DevPipelineWorkflow + run_dev_task activity
    Dockerfile    — Python 3.12 + OpenHands + docker CLI
  qa/             — QA review pod (LLM + git diff)
    worker.py     — run_qa_review activity
    prompts/      — QA review system prompt
    Dockerfile    — Python 3.12 + temporalio + httpx + git
k8s/
  namespace.yaml
  temporal/       — Temporal server (Postgres-backed) + UI
  ollama/         — Ollama deployment with hostPath mount of ~/.ollama
  agents/         — planning, agent, qa Deployments
  api/            — orchestrator API Deployment + NodePort Service
scripts/          — setup-minikube, build-images, deploy-all, create-git-secret
docker-compose.yaml  — local dev: Temporal + API + Planning + Agent + QA
```

## 6-Phase BMAD Pipeline

```
DevPipelineWorkflow (Temporal)
  │
  ├─ classify_task        (planning-queue) → SIMPLE or COMPLEX
  ├─ [if COMPLEX]:
  │   ├─ run_analyst      (planning-queue) → project brief
  │   ├─ run_pm           (planning-queue) → PRD + acceptance criteria
  │   ├─ run_architect    (planning-queue) → technical design
  │   └─ run_scrum_master (planning-queue) → implementation stories
  ├─ run_dev_task         (agent-queue)    → OpenHands: code + test + commit
  └─ run_qa_review        (qa-queue)       → verdict: APPROVED / REJECTED
```

**Quick Flow:** Simple tasks (typo fix, add endpoint) skip planning phases and go straight to Developer.

## Task queues

- `planning-queue` → Planning pod (analyst, PM, architect, scrum master, classifier)
- `agent-queue` → Developer pod (OpenHands CodeActAgent) + DevPipelineWorkflow
- `qa-queue` → QA pod (review git diff against PRD)

## Key design decisions

- **BMAD-structured pipeline**: Instead of sending a raw one-liner to OpenHands, the planning pods produce structured artifacts (brief → PRD → architecture → stories) that give the Developer dramatically better context.
- **3 pods, 3 queues, 1 workflow**: Planning pod is lightweight (LLM-only). Agent pod runs OpenHands. QA pod reads git diffs. The workflow orchestrates all three from the agent worker.
- **Quick flow bypass**: A classifier LLM call determines if the task is simple enough to skip planning (e.g., "fix typo"). Avoids 15+ minutes of unnecessary planning for trivial tasks.
- **Temporal** handles workflow durability — pod crashes replay from last checkpoint automatically. Heartbeats fire every 60s to keep long-running LLM tasks alive.
- **OpenHands** (CodeActAgent) is the AI engine for code execution. Planning and QA pods call Ollama directly via httpx — no OpenHands overhead.
- **Ollama** runs on the host machine (local dev) or as a K8s pod. Uses `hostPath` volume mount so models don't need re-downloading.

## LLM

Any Ollama-compatible model via env vars. Recommended: `qwen2.5-coder:14b` (local dev) or `qwen3-coder:30b` (K8s). Temperature 0.1-0.2 for deterministic output.

- `PLANNING_MODEL` — model for planning activities (default: `qwen2.5-coder:14b`)
- `MODEL` — model for OpenHands agent (default: `ollama/qwen2.5-coder:14b`)
- `QA_MODEL` — model for QA review (default: `qwen2.5-coder:14b`)
