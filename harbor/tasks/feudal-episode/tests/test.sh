#!/usr/bin/env bash
# Harbor verifier entry: produce /logs/verifier/reward.json
set -euo pipefail
mkdir -p /logs/verifier
python3 /tests/verify.py
