# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

Autowright is an autonomous AI software development platform. A human manager sends requirements via a Web UI, and an AI agent (powered by OpenHands) clones repos, writes code, self-reviews, and commits — all orchestrated by Temporal for crash-proof durability.

**Pipeline:** Manager chat → FastAPI → Temporal Workflow → Agent pod (OpenHands) → committed code

## Commands

### Local dev (no Minikube needed)
```bash
# Start Temporal + API + Agent
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
web/          Next.js 15 UI  (ChatInput, TaskFeed, PodStatus)
api/          FastAPI orchestrator
  main.py         — app entrypoint, CORS
  routes/tasks.py — POST /tasks starts Temporal workflow on agent-queue
  routes/ws.py    — WebSocket /ws/{task_id} polls workflow status
  activities/     — activity stub (for IDE import only)
agents/
  agent/          — Temporal worker + OpenHands runner (single self-contained pod)
    worker.py     — workflow + activity definitions, OpenHands subprocess, heartbeats
    Dockerfile    — Python 3.12 + OpenHands + docker CLI
k8s/
  namespace.yaml
  temporal/       — Temporal server (Postgres-backed) + UI
  ollama/         — Ollama deployment with hostPath mount of ~/.ollama
  agents/         — agent Deployment
  api/            — orchestrator API Deployment + NodePort Service
scripts/          — setup-minikube, build-images, deploy-all, create-git-secret
docker-compose.yaml  — local dev: Temporal + API + Agent (no Minikube)
```

## Key design decisions

- **Single agent pod** handles the full pipeline: clone → implement → self-review → commit. The workflow and activity both live in `agents/agent/worker.py` on a single task queue (`agent-queue`).
- **Temporal** handles workflow durability — pod crashes replay from last checkpoint automatically. Heartbeats fire every 60s to keep long-running LLM tasks alive.
- **OpenHands** (CodeActAgent) is the AI engine. The agent pod runs it as a subprocess with a structured 7-step task prompt.
- **Ollama** runs on the host machine (local dev) or as a K8s pod. Uses `hostPath` volume mount so models don't need re-downloading.
- **Docker runtime** (local dev): OpenHands spawns sandbox containers via Docker socket. **Local runtime** (K8s): sandbox runs as subprocess inside the agent pod.

## LLM

Any Ollama-compatible model via `MODEL` env var. Recommended: `qwen2.5-coder:14b` or `qwen3-coder:30b`. Temperature 0.1 for deterministic output.
