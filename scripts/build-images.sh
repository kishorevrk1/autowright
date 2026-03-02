#!/usr/bin/env bash
# Build all Docker images and load them into Minikube's internal registry.
# Must be run after `minikube start`.

set -euo pipefail

# Point Docker daemon at Minikube's registry
eval "$(minikube docker-env)"

echo "==> Building planning image..."
docker build -t openclaw/planning:latest agents/planning/

echo "==> Building agent image..."
docker build -t openclaw/agent:latest -f agents/agent/Dockerfile .

echo "==> Building QA image..."
docker build -t openclaw/qa:latest agents/qa/

echo "==> Building orchestrator API image..."
docker build -t openclaw/orchestrator-api:latest api/

echo "==> All images built."
echo "    Next: run ./scripts/deploy-all.sh"
