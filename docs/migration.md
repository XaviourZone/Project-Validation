# Legacy database migration

The old validation-docker implementation used SQLite for:

1. WRS reference database
2. PANS reference database
3. NSC reference database
4. Router file lifecycle state
5. Parser AIS state
6. Parser track/reference state
7. Forwarder delivery state

Project-Validation is being migrated to **RocksDB for all seven stores**. There is no SQLite runtime database in the target architecture.

## Target storage

- parser/reference/wrs
- parser/reference/pans
- parser/reference/nsc
- router/state
- parser/state/ais
- parser/state/track
- forwarder/state/delivery

Each store is a RocksDB directory. JSON is used as the document encoding while logical namespaces and keys provide deterministic access.

## Migration

Use migration/migrate_sqlite_to_rocksdb.py once against copies of the legacy .db files. It preserves all tables and rows and writes migration_manifest.json.

The application migration is separate from the data migration: runtime code must open only the RocksDB stores. The legacy SQLite files are never opened by Router, Parser or Forwarder after cutover.

## Required validation before retirement

- source table row counts equal migrated counts
- WRS/PANS/NSC identity lookups return the same records
- AIS track state and MMSI reference state survive restart
- Router duplicate/lifecycle state survives restart
- Forwarder delivery state survives restart
- no service imports sqlite3
- no runtime configuration points to a .db file
