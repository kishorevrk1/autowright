# Autowright

**Autonomous AI software development platform with crash-proof durability.**

Submit requirements in plain English → get committed code back. Zero API costs, zero code exfiltration, fully self-hosted.

## What it does

A human manager types a requirement ("Add a /health endpoint") and a repo URL into the web UI. Autowright's AI agent autonomously:

1. Clones the repo
2. Explores the codebase
3. Implements the requirement
4. Runs tests
5. Self-reviews via `git diff`
6. Commits to a feature branch
7. Pushes the branch to remote
8. Reports back with branch name, commit SHA, and summary

> **Roadmap:** Auto-deploy (build Docker image → write K8s manifests → deploy to cluster) is planned as an optional pipeline stage.

All orchestrated by [Temporal](https://temporal.io) — if the agent pod crashes mid-task, Temporal automatically replays from the last checkpoint. No lost work.

## Architecture

```
┌────────────────────────────────────┐
│     Web UI (Next.js 15)            │
│     Chat input + live task feed    │
└──────────────┬─────────────────────┘
               │ REST + WebSocket
┌──────────────▼─────────────────────┐
│     API (FastAPI)                  │
│     Starts workflows, streams      │
│     status via WebSocket           │
└──────────────┬─────────────────────┘
               │ Temporal SDK
┌──────────────▼─────────────────────┐
│     Temporal Server                │
│     Durable workflow orchestration │
└──────────────┬─────────────────────┘
               │
┌──────────────▼─────────────────────┐
│     Agent Pod                      │
│     OpenHands (CodeActAgent)       │
│  Clone → Code → Test → Commit → Push │
└──────────────┬─────────────────────┘
               │
┌──────────────▼─────────────────────┐
│     Ollama (local LLM)            │
│     qwen2.5-coder / qwen3-coder  │
└────────────────────────────────────┘
```

## Quick Start

### Prerequisites
- Docker Desktop
- Node.js 18+
- [Ollama](https://ollama.ai) with a coding model pulled:
  ```bash
  ollama pull qwen2.5-coder:14b
  ```

### Run locally

```bash
# Start Temporal + API + Agent
docker compose up

# In another terminal — start the Web UI
cd web && npm install && npm run dev
```

Open [http://localhost:3000](http://localhost:3000) and submit a task.

### Monitor

- **Web UI**: [http://localhost:3000](http://localhost:3000) — submit tasks, see live status
- **Temporal UI**: [http://localhost:8080](http://localhost:8080) — workflow history, retry status
- **API**: [http://localhost:8000/docs](http://localhost:8000/docs) — FastAPI docs

### Submit via API

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/you/repo",
    "requirement": "Add a /health endpoint"
  }'
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| AI Engine | [OpenHands](https://github.com/All-Hands-AI/OpenHands) (CodeActAgent) |
| Workflow | [Temporal](https://temporal.io) (durable, crash-proof) |
| LLM | [Ollama](https://ollama.ai) (local, any model) |
| API | FastAPI (Python 3.12) |
| Web UI | Next.js 15 + Tailwind + shadcn/ui |
| Infra | Docker Compose (local) / Minikube (K8s) |

## Why Autowright?

| Feature | Autowright | Devin | OpenHands | SWE-agent |
|---------|-----------|-------|-----------|-----------|
| Open source | Yes | No | Yes | Yes |
| Self-hosted | Yes | No | Yes | Yes |
| Crash-proof (Temporal) | **Yes** | No | No | No |
| Manager-facing UI | **Yes** | Yes | No | No |
| Local LLM (no API costs) | **Yes** | No | Yes | Yes |
| Auto-retry on failure | **Yes** | ? | No | No |

## Kubernetes Deployment

```bash
# One-time setup
./scripts/setup-minikube.sh
./scripts/create-git-secret.sh ~/.ssh/id_rsa

# Build images + deploy
./scripts/build-images.sh
./scripts/deploy-all.sh
```

## Configuration

Key environment variables (set in `docker-compose.yaml`):

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL` | `ollama/qwen2.5-coder:14b` | Ollama model name |
| `OLLAMA_HOST` | `http://host.docker.internal:11434` | Ollama API URL |
| `TEMPORAL_HOST` | `temporal:7233` | Temporal server address |
| `RUNTIME_TYPE` | `docker` | `docker` (local) or `local` (K8s) |

## License

MIT
