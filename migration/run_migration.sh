#!/usr/bin/env bash
set -euo pipefail

ROOT="${VALIDATION_HOME:-$(cd "$(dirname "$0")/.." && pwd)}"
TARGET="${ROCKSDB_ROOT:-$ROOT/runtime/rocksdb}"

python3 "$ROOT/migration/migrate_sqlite_to_rocksdb.py" \
  --source "${WRS_SQLITE:-$ROOT/Validation/Database/WRS/wrs.db}" \
  --source "${PANS_SQLITE:-$ROOT/Validation/Database/PANS/pans.db}" \
  --source "${NSC_SQLITE:-$ROOT/Validation/Database/NSC/nsc.db}" \
  --source "${ROUTER_SQLITE:-$ROOT/state/router_state.db}" \
  --source "${AIS_STATE_SQLITE:-$ROOT/Validation/state/ais_state.db}" \
  --source "${TRACK_STATE_SQLITE:-$ROOT/Validation/state/track_state.db}" \
  --source "${FORWARDER_SQLITE:-$ROOT/Validation/Data_Forwarder/state/forwarder.db}" \
  --target-root "$TARGET"

echo "RocksDB migration target: $TARGET"
