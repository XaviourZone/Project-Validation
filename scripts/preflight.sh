#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
python3 --version
python3 - <<'PY'
import importlib.util
missing=[m for m in ("yaml","rocksdb") if importlib.util.find_spec(m) is None]
if missing:
    raise SystemExit("Missing Python modules: "+", ".join(missing))
print("PASS: PyYAML and RocksDB Python bindings available")
PY
for d in router parser forwarder shared; do test -d "$d" || { echo "MISSING $d"; exit 1; }; done
if grep -R --include='*.py' -nE '^[[:space:]]*(import|from)[[:space:]]+sqlite3\\b' router parser forwarder shared; then
  echo "FAIL: SQLite runtime import detected"
  exit 1
fi
echo "PASS: no SQLite runtime import in services"
echo "PASS: repository structure"
