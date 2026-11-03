#!/usr/bin/env bash
# Vendor the local feudal-sim checkout into the Harbor task build context.
# Run from the repo root:  bash harbor/tasks/feudal-episode/prepare.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
TASK_DIR="$REPO_ROOT/harbor/tasks/feudal-episode"

echo "📦 Vendoring $REPO_ROOT → $TASK_DIR/environment/feudal-sim.tar.gz"
# COPYFILE_DISABLE: no macOS AppleDouble (._*) files in the tarball.
# renderer*.so excluded: the .so is a macOS Mach-O build artifact; Linux
# containers must have NO .so present (guarded imports treat it as headless).
COPYFILE_DISABLE=1 tar czf "$TASK_DIR/environment/feudal-sim.tar.gz" \
    -C "$REPO_ROOT" \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='runs' \
    --exclude='logs' \
    --exclude='mlruns*' \
    --exclude='mlartifacts' \
    --exclude='render/build' \
    --exclude='render/CMakeFiles' \
    --exclude='feudal_sim/renderer*.so' \
    --exclude='render/renderer*.so' \
    --exclude='.claude' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='.ruff_cache' \
    --exclude='harbor' \
    .
echo "✅ done"
