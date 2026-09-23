#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export VALIDATION_HOME="$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

mkdir -p "$ROOT/DATA_INFLOW"/{SAIS_IOR,SAIS_GLOBAL,MSIS,LRIT}
mkdir -p "$ROOT/forwarder/spool"/{pending,delivered,failed}
mkdir -p "$ROOT/router/state" "$ROOT/parser/state" "$ROOT/parser/reference" "$ROOT/forwarder/state" "$ROOT/logs"

echo "[VALIDATION] Starting single-port operator console on http://127.0.0.1:8080"
exec python3 -m console.app.main
