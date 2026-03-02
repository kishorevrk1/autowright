# Autowright

**BMAD-structured autonomous AI software development platform with crash-proof durability.**

Submit requirements in plain English → AI plans, architects, codes, reviews, and commits. Zero API costs, zero code exfiltration, fully self-hosted.

## What it does

A human manager types a requirement and repo URL into the web UI. Autowright's AI pipeline autonomously:

1. **Classifies** the task as simple or complex
2. **Analyzes** the requirement and codebase (BMAD Analyst)
3. **Plans** structured requirements with acceptance criteria (BMAD Product Manager)
4. **Architects** the technical design — files to modify, patterns to follow (BMAD Architect)
5. **Breaks down** work into ordered implementation stories (BMAD Scrum Master)
6. **Implements** via OpenHands CodeActAgent — clone, code, test, commit, push
7. **Reviews** the diff against the PRD and returns a QA verdict

Simple tasks ("fix typo", "add health endpoint") skip steps 2-5 via **quick flow**.

All orchestrated by [Temporal](https://temporal.io) — if any pod crashes mid-task, Temporal automatically replays from the last checkpoint. No lost work.

## Architecture

```
┌────────────────────────────────────────────┐
│     Web UI (Next.js 15)                    │
│     Chat input + pipeline stepper          │
└──────────────┬─────────────────────────────┘
               │ REST + WebSocket
┌──────────────▼─────────────────────────────┐
│     API (FastAPI)                          │
│     Starts workflows, streams status       │
└──────────────┬─────────────────────────────┘
               │ Temporal SDK
┌──────────────▼─────────────────────────────┐
│     Temporal Server                        │
│     Durable workflow orchestration         │
└──────────────┬─────────────────────────────┘
               │
     ┌─────────┴──────────┐
     │                    │
┌────▼─────────────┐ ┌───▼──────────────────┐
│ Planning Pod     │ │  Developer Pod       │
│ (LLM-only)      │ │  (OpenHands)         │
│                  │ │                      │
│ • Classifier     │ │  Clone → Code →     │
│ • Analyst        │ │  Test → Review →    │
│ • PM             │ │  Commit → Push      │
│ • Architect      │ │                      │
│ • Scrum Master   │ └───┬──────────────────┘
└──────────────────┘     │
                    ┌────▼─────────────────┐
                    │  QA Pod              │
                    │  (LLM + git diff)    │
                    │                      │
                    │  Review diff vs PRD  │
                    │  → APPROVED/REJECTED │
                    └────┬─────────────────┘
                         │
                    ┌────▼─────────────────┐
                    │  Ollama (local LLM)  │
                    │  qwen2.5-coder /     │
                    │  qwen3-coder         │
                    └──────────────────────┘
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
# Start Temporal + API + Planning + Agent + QA
docker compose up

# In another terminal — start the Web UI
cd web && npm install && npm run dev
```

Open [http://localhost:3000](http://localhost:3000) and submit a task.

### Monitor

- **Web UI**: [http://localhost:3000](http://localhost:3000) — submit tasks, pipeline stepper shows each phase
- **Temporal UI**: [http://localhost:8080](http://localhost:8080) — workflow history, 3 task queues
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

## BMAD Method Integration

Autowright uses the [BMAD method](https://docs.bmad-method.org/) (Build More, Architect Dreams) to structure its planning pipeline. Each planning phase uses a specialized AI persona with a focused system prompt:

| Phase | BMAD Role | Output | Task Queue |
|-------|-----------|--------|------------|
| Classify | Classifier | SIMPLE / COMPLEX | planning-queue |
| Analyze | Analyst | Project brief | planning-queue |
| Plan | Product Manager | PRD + acceptance criteria | planning-queue |
| Architect | Software Architect | Technical design | planning-queue |
| Stories | Scrum Master | Implementation stories (JSON) | planning-queue |
| Develop | Developer (OpenHands) | Code + tests + commit | agent-queue |
| Review | QA Engineer | Verdict (APPROVED/REJECTED) | qa-queue |

## Tech Stack

| Component | Technology |
|-----------|-----------|
| AI Engine | [OpenHands](https://github.com/All-Hands-AI/OpenHands) (CodeActAgent) |
| Planning | [BMAD Method](https://docs.bmad-method.org/) (AI personas) |
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
| BMAD planning pipeline | **Yes** | No | No | No |
| Manager-facing UI | **Yes** | Yes | No | No |
| Local LLM (no API costs) | **Yes** | No | Yes | Yes |
| Auto-retry on failure | **Yes** | ? | No | No |
| QA review phase | **Yes** | No | No | No |

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
| `PLANNING_MODEL` | `qwen2.5-coder:14b` | Ollama model for planning phases |
| `MODEL` | `ollama/qwen2.5-coder:14b` | Ollama model for OpenHands agent |
| `QA_MODEL` | `qwen2.5-coder:14b` | Ollama model for QA review |
| `OLLAMA_HOST` | `http://host.docker.internal:11434` | Ollama API URL |
| `TEMPORAL_HOST` | `temporal:7233` | Temporal server address |
| `RUNTIME_TYPE` | `docker` | `docker` (local) or `local` (K8s) |

## License

MIT
