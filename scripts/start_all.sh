#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export VALIDATION_HOME="$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
cd "$ROOT"
mkdir -p "$ROOT/DATA_INFLOW"/{SAIS_IOR,SAIS_GLOBAL,MSIS,LRIT} "$ROOT/forwarder/spool"/{pending,delivered,failed} "$ROOT/router/state" "$ROOT/parser/state" "$ROOT/parser/reference" "$ROOT/forwarder/state" "$ROOT/logs" "$ROOT/run"
start_one() {
  local name="$1"; shift
  local log="$ROOT/logs/$name.log"; local pidfile="$ROOT/run/$name.pid"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then echo "[VALIDATION] $name already running (PID $(cat "$pidfile"))"; return; fi
  nohup env VALIDATION_HOME="$ROOT" PYTHONPATH="$PYTHONPATH" python3 "$@" >>"$log" 2>&1 < /dev/null &
  echo $! > "$pidfile"; echo "[VALIDATION] $name started (PID $!)"
}
start_one router -m router.app.main --config router/config/sources.yaml
start_one parser -m parser.app.main --config parser/config/parser.yaml
start_one forwarder -m forwarder.app.main --config forwarder/config/forwarder.yaml
start_one console -m console.app.main
echo
echo "VALIDATION started as independent processes."
echo "Console:   http://127.0.0.1:8080"
echo "Router:    http://127.0.0.1:18080"
echo "Parser:    http://127.0.0.1:18081"
echo "Forwarder: http://127.0.0.1:18082"
echo "PID files: $ROOT/run/"
