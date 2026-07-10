#!/usr/bin/env bash
# Run the simulation and tee all output (stdout + stderr) to a timestamped log file.
# Usage: ./run.sh [any main.py args]
#   e.g. ./run.sh --debug

set -euo pipefail

LOGS_DIR="$(dirname "$0")/logs"
mkdir -p "$LOGS_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOGS_DIR/sim_${TIMESTAMP}.log"

echo "Logging to: $LOG_FILE"
echo "---"

# Point MLflow at the local tracking server if one is actually running;
# otherwise fall back to the local file store (mlruns/). Hard-pointing at a
# dead server makes mlflow.set_experiment() hang in HTTP retries at startup.
if curl -s --max-time 1 http://127.0.0.1:5000/health >/dev/null 2>&1; then
    export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
    echo "MLflow: using tracking server at 127.0.0.1:5000"
else
    export MLFLOW_TRACKING_URI="sqlite:///mlruns.db"
    echo "MLflow: no server on :5000, using local sqlite store (mlruns.db)"
fi

# Merge stderr into stdout so both go to the tee
uv run main.py "$@" 2>&1 | tee "$LOG_FILE"
