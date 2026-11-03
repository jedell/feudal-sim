#!/usr/bin/env bash
# Oracle solution: run a short AI-free episode — fast, free, deterministic.
# Validates the environment + verifier end-to-end without API keys.
set -euo pipefail

TASK="${FEUDAL_TASK:-{\"seed\": 1, \"max_turns\": 4, \"ai_enabled\": false}}"

mkdir -p /logs/episode
/app/.venv/bin/python -m feudal_sim.rl.episode \
    --task "$TASK" \
    --out-dir /logs/episode \
    --quiet
