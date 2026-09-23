#!/usr/bin/env python3
"""ONE-TIME legacy SQLite -> RocksDB migration utility."""
from __future__ import annotations
import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any
from shared.storage.rocksdb_store import RocksDBStore

def migrate_one(source: Path, target: Path, database_name: str) -> dict[str, Any]:
    if not source.exists():
        raise FileNotFoundError(source)
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Target RocksDB already exists and is non-empty: {target}")
    store = RocksDBStore(target)
    manifest = {"source": str(source), "target": str(target), "database": database_name, "tables": {}}
    conn = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        tables = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )]
        for table in tables:
            columns = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
            count = 0
            for row in conn.execute(f'SELECT * FROM "{table}"'):
                document = {column: row[column] for column in columns}
                store.put(f"{database_name}/{table}", str(count), document)
                count += 1
            manifest["tables"][table] = {"columns": columns, "rows": count}
    finally:
        conn.close()
        store.put("__migration__", "manifest", manifest)
        store.close()
    return manifest

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", action="append", required=True, help="Legacy SQLite .db path; repeat for each database")
    ap.add_argument("--target-root", required=True, help="Root directory for migrated RocksDB stores")
    args = ap.parse_args()
    root = Path(args.target_root)
    root.mkdir(parents=True, exist_ok=True)
    reports = []
    for source_arg in args.source:
        source = Path(source_arg)
        report = migrate_one(source, root / source.stem, source.stem)
        reports.append(report)
        print(f"MIGRATED {source} -> {root / source.stem}")
        for table, info in report["tables"].items():
            print(f"  {table}: {info['rows']} rows")
    (root / "migration_manifest.json").write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Migration complete: {root / 'migration_manifest.json'}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
