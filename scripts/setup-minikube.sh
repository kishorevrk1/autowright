#!/usr/bin/env bash
# Bootstrap Minikube with enough resources for Ollama (qwen3-coder:30b)
# and all openclaw pods. Run once before deploying.

set -euo pipefail

echo "==> Starting Minikube..."
minikube start \
  --cpus=8 \
  --memory=24g \
  --disk-size=80g \
  --driver=docker \
  --addons=registry

echo "==> Enabling Minikube registry..."
minikube addons enable registry

echo "==> Creating openclaw namespace..."
kubectl apply -f k8s/namespace.yaml

echo "==> Done. Next: run ./scripts/build-images.sh"
