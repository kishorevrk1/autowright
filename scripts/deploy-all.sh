#!/usr/bin/env bash
# Deploy all K8s manifests to the local Minikube cluster.

set -euo pipefail

echo "==> Applying namespace..."
kubectl apply -f k8s/namespace.yaml

echo "==> Deploying Temporal..."
kubectl apply -f k8s/temporal/

echo "==> Waiting for Temporal to be ready..."
kubectl rollout status deployment/temporal -n openclaw --timeout=120s

echo "==> Deploying Ollama..."
kubectl apply -f k8s/ollama/

echo "==> Waiting for Ollama..."
kubectl rollout status deployment/ollama -n openclaw --timeout=180s

echo "==> Deploying agent pods..."
kubectl apply -f k8s/agents/

echo "==> Deploying orchestrator API..."
kubectl apply -f k8s/api/

echo ""
echo "==> All pods:"
kubectl get pods -n openclaw

echo ""
echo "==> Access:"
echo "    Temporal UI : kubectl port-forward svc/temporal-ui  8080:8080 -n openclaw"
echo "    API         : kubectl port-forward svc/orchestrator-api 8000:8000 -n openclaw"
echo "    Web UI      : cd web && npm run dev   (runs at http://localhost:3000)"
