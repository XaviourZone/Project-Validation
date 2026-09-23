#!/usr/bin/env bash
set -euo pipefail
ROOT="${VALIDATION_HOME:-$(cd "$(dirname "$0")/.." && pwd)}"
LEGACY_ROOT="${LEGACY_VALIDATION_HOME:-$ROOT/../validation-docker}"
migrate(){ local src="$1" target="$2"; [ -f "$src" ] || { echo "MISSING legacy DB: $src" >&2; exit 1; }; python3 "$ROOT/migration/migrate_sqlite_to_rocksdb.py" --source "$src" --target-root "$target"; }
migrate "${WRS_SQLITE:-$LEGACY_ROOT/Validation/Database/WRS/wrs.db}" "$ROOT/parser/reference"
migrate "${PANS_SQLITE:-$LEGACY_ROOT/Validation/Database/PANS/pans.db}" "$ROOT/parser/reference"
migrate "${NSC_SQLITE:-$LEGACY_ROOT/Validation/Database/NSC/nsc.db}" "$ROOT/parser/reference"
migrate "${ROUTER_SQLITE:-$LEGACY_ROOT/state/router_state.db}" "$ROOT/router/state"
migrate "${AIS_STATE_SQLITE:-$LEGACY_ROOT/Validation/state/ais_state.db}" "$ROOT/parser/state"
migrate "${TRACK_STATE_SQLITE:-$LEGACY_ROOT/Validation/state/track_state.db}" "$ROOT/parser/state"
migrate "${FORWARDER_SQLITE:-$LEGACY_ROOT/Validation/Data_Forwarder/state/forwarder.db}" "$ROOT/forwarder/state"
echo "All legacy SQLite stores migrated to RocksDB runtime locations."
