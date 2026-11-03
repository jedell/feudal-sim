#!/usr/bin/env bash
# Vendor the local feudal-sim checkout into the Harbor task build context.
# Run from the repo root:  bash harbor/tasks/feudal-episode/prepare.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
TASK_DIR="$REPO_ROOT/harbor/tasks/feudal-episode"

echo "📦 Vendoring $REPO_ROOT → $TASK_DIR/environment/feudal-sim.tar.gz"
tar czf "$TASK_DIR/environment/feudal-sim.tar.gz" \
    -C "$REPO_ROOT" \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='runs' \
    --exclude='logs' \
    --exclude='mlruns*' \
    --exclude='mlartifacts' \
    --exclude='render/build' \
    --exclude='render/CMakeFiles' \
    --exclude='.claude' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='.ruff_cache' \
    --exclude='harbor' \
    .
echo "✅ done"
