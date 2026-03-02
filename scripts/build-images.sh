#!/usr/bin/env bash
# Build all Docker images and load them into Minikube's internal registry.
# Must be run after `minikube start`.

set -euo pipefail

# Point Docker daemon at Minikube's registry
eval "$(minikube docker-env)"

echo "==> Building base agent image..."
docker build -t openclaw/agent-base:latest agents/base/

echo "==> Building code-writer image..."
docker build -t openclaw/agent-code-writer:latest agents/code-writer/

echo "==> Building reviewer image..."
docker build -t openclaw/agent-reviewer:latest agents/reviewer/

echo "==> Building deployer image..."
docker build -t openclaw/agent-deployer:latest agents/deployer/

echo "==> Building orchestrator API image..."
docker build -t openclaw/orchestrator-api:latest api/

echo "==> All images built."
echo "    Next: run ./scripts/deploy-all.sh"
