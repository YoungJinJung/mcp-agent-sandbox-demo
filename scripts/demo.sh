#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
CLUSTER=mcp-agent-sandbox-demo
export KUBECONFIG="$ROOT/.state/kubeconfig"
export KIND_EXPERIMENTAL_PROVIDER=docker
NODE_IMAGE='kindest/node:v1.35.8@sha256:07b2536e30b803ed61d1677a79df6115f798ce64c80f9e22f6ed45afd09323c0'

k() { kubectl --kubeconfig "$KUBECONFIG" --context "kind-$CLUSTER" "$@"; }
need() { command -v "$1" >/dev/null || { echo "Install $1 first (see README)." >&2; exit 1; }; }

case "${1:-help}" in
  up)
    for tool in docker kind kubectl curl python3; do need "$tool"; done
    docker info >/dev/null
    mkdir -p .state
    # An exported, dedicated kubeconfig keeps the user's current context intact.
    if kind get clusters | grep -Fxq "$CLUSTER"; then
      kind export kubeconfig --name "$CLUSTER" --kubeconfig "$KUBECONFIG"
    else
      kind create cluster --name "$CLUSTER" --image "$NODE_IMAGE" \
        --kubeconfig "$KUBECONFIG" --wait 180s
    fi
    curl -fL --retry 3 \
      https://github.com/kubernetes-sigs/agent-sandbox/releases/download/v1.0.4/sandbox-with-extensions.yaml \
      -o .state/controller.yaml
    python3 - <<'PY'
import hashlib
from pathlib import Path
expected = "8cbe7f4c252463667e2286993bd735cb33bb2e47d7f304b92aa2ca97f57052c0"
actual = hashlib.sha256(Path(".state/controller.yaml").read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit("Controller manifest checksum mismatch")
PY
    k apply --server-side -f .state/controller.yaml
    k wait --for=condition=Established --timeout=90s \
      crd/sandboxes.agents.x-k8s.io \
      crd/sandboxclaims.extensions.agents.x-k8s.io \
      crd/sandboxtemplates.extensions.agents.x-k8s.io \
      crd/sandboxwarmpools.extensions.agents.x-k8s.io
    k -n agent-sandbox-system rollout status deployment/agent-sandbox-controller --timeout=180s
    docker build -t mcp-agent-sandbox-demo:local .
    kind load docker-image mcp-agent-sandbox-demo:local --name "$CLUSTER"
    k apply -f k8s/demo.yaml
    k -n mcp-demo rollout status deployment/mcp-server --timeout=180s
    echo 'Ready. Run: make demo'
    ;;
  run)
    for tool in kubectl uv curl; do need "$tool"; done
    test -f "$KUBECONFIG" || { echo 'Run make up first.' >&2; exit 1; }
    test -x .venv/bin/python || uv venv --python 3.12 .venv
    uv pip sync --python .venv/bin/python --require-hashes requirements.lock
    # Wait for this port-forward process, not any service already using the port.
    kubectl --kubeconfig "$KUBECONFIG" --context "kind-$CLUSTER" \
      -n mcp-demo port-forward --address 127.0.0.1 service/mcp-server 18000:8000 \
      > .state/port-forward.log 2>&1 &
    forward_pid=$!
    trap 'kill "$forward_pid" 2>/dev/null || true; wait "$forward_pid" 2>/dev/null || true' EXIT
    ready=false
    for ((i=0; i<60; i++)); do
      kill -0 "$forward_pid" 2>/dev/null || { cat .state/port-forward.log >&2; exit 1; }
      if grep -q 'Forwarding from 127.0.0.1:18000' .state/port-forward.log \
          && curl -fsS http://127.0.0.1:18000/readyz >/dev/null; then
        ready=true
        break
      fi
      sleep 1
    done
    "$ready" || { cat .state/port-forward.log >&2; exit 1; }
    .venv/bin/python demo.py | tee .state/last-run.log
    k -n mcp-demo wait --for=delete sandboxclaims --all --timeout=60s
    echo 'PASS: MCP round trip completed; no demo claims remain.'
    ;;
  status)
    k -n mcp-demo get pods,sandboxes,sandboxclaims,sandboxwarmpools
    ;;
  down)
    need kind
    kind delete cluster --name "$CLUSTER" --kubeconfig "$KUBECONFIG"
    ;;
  *)
    echo 'Usage: scripts/demo.sh {up|run|status|down}'
    ;;
esac
