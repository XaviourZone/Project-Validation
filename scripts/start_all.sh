#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
mkdir -p "$ROOT/logs" "$ROOT/run"
"$PY" "$ROOT/standalone/db/start_postgres.py"
start_one() {
  local name="$1"; shift
  local pidfile="$ROOT/run/standalone-$name.pid"
  local logfile="$ROOT/logs/standalone-$name.log"
  if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "$name already running (PID $(cat "$pidfile"))"; return
  fi
  nohup "$PY" "$@" >>"$logfile" 2>&1 < /dev/null &
  echo $! >"$pidfile"
  echo "$name started (PID $!)"
}
start_one db_manager "$ROOT/standalone/db/db_manager.py"
for feed in SAIS_IOR SAIS_GLOBAL MSIS LRIT VATMS_EAST VATMS_WEST NAIS; do
  start_one "$feed" "$ROOT/standalone/feeds/$feed.py"
done
echo "VALIDATION standalone runtime started"
echo "DB console: http://127.0.0.1:5055"
