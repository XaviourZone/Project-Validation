#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
"$ROOT/linux-x64/bin/pg_ctl" -D "$ROOT/data" stop -m fast
