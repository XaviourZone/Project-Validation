#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export VALIDATION_HOME="$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$ROOT/logs"
cd "$ROOT"
exec python3 -m forwarder.app.main --config forwarder/config/forwarder.yaml
