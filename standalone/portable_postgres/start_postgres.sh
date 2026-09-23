#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PG="$ROOT/linux-x64"; DATA="$ROOT/data"
[[ -x "$PG/bin/initdb" ]] || { echo "ERROR: PostgreSQL binaries missing" >&2; exit 1; }
if [[ ! -f "$DATA/PG_VERSION" ]]; then mkdir -p "$DATA"; "$PG/bin/initdb" -D "$DATA" -U validation -A scram-sha-256 -E UTF8; fi
if "$PG/bin/pg_ctl" -D "$DATA" status >/dev/null 2>&1; then echo "PostgreSQL already running"; exit 0; fi
"$PG/bin/pg_ctl" -D "$DATA" -l "$ROOT/postgres.log" -o "-p 5432" start
