#!/usr/bin/env bash
# Create the git SSH key secret used by all agent pods.
# Usage: ./scripts/create-git-secret.sh ~/.ssh/id_rsa

set -euo pipefail

KEY_PATH="${1:-$HOME/.ssh/id_rsa}"

if [[ ! -f "$KEY_PATH" ]]; then
  echo "ERROR: SSH key not found at $KEY_PATH"
  exit 1
fi

kubectl create secret generic git-ssh-key \
  --from-file=id_rsa="$KEY_PATH" \
  -n openclaw \
  --dry-run=client -o yaml | kubectl apply -f -

echo "==> git-ssh-key secret created/updated in namespace openclaw"
