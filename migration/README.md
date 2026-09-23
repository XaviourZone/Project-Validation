# Database migration

The Validation runtime uses **RocksDB only**. SQLite is a legacy source format and is not used by Router, Parser, Forwarder, or runtime state.

## Legacy databases to migrate

- WRS: Validation/Database/WRS/wrs.db
- PANS: Validation/Database/PANS/pans.db
- NSC: Validation/Database/NSC/nsc.db
- Router state: state/router_state.db
- Parser AIS state: Validation/state/ais_state.db
- Parser track/reference state: Validation/state/track_state.db
- Forwarder delivery state: Validation/Data_Forwarder/state/forwarder.db

The first three are authoritative reference data. The remaining databases are runtime state and must also be migrated so there is no SQLite runtime dependency.

## Migration rule

The one-time migration utility preserves every legacy table/row as JSON in RocksDB and produces migration_manifest.json with source/table/row counts. The migrated data is then consumed through RocksDB adapters; SQLite files are not opened by the services.

Do not delete the legacy files until the manifest counts and application-level lookup tests have passed.
