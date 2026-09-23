#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export VALIDATION_HOME="$ROOT"
export PYTHONPATH="$ROOT\${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$ROOT/DATA_INFLOW"/{SAIS_IOR,SAIS_GLOBAL,MSIS,LRIT} "$ROOT/forwarder/spool"/{pending,delivered,failed} "$ROOT/router/state" "$ROOT/parser/state" "$ROOT/parser/reference" "$ROOT/forwarder/state" "$ROOT/logs"
PIDS=()
cleanup(){ trap - INT TERM EXIT; for p in "\${PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done; wait || true; }
trap cleanup INT TERM EXIT
echo "[VALIDATION] Starting Forwarder"; python3 -m forwarder.app.main --config "$ROOT/forwarder/config/forwarder.yaml" >"$ROOT/logs/forwarder.log" 2>&1 & PIDS+=("$!")
sleep 1
echo "[VALIDATION] Starting Parser"; python3 -m parser.app.main --config "$ROOT/parser/config/parser.yaml" >"$ROOT/logs/parser.log" 2>&1 & PIDS+=("$!")
sleep 2
echo "[VALIDATION] Starting Router"; python3 -m router.app.main --config "$ROOT/router/config/sources.yaml" >"$ROOT/logs/router.log" 2>&1 & PIDS+=("$!")
echo "[VALIDATION] Services started: forwarder=\${PIDS[0]} parser=\${PIDS[1]} router=\${PIDS[2]}"
wait
