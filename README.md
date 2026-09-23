# Project-Validation

Offline maritime/AIS validation pipeline with three independent services that cooperate over local interfaces.

## Runtime architecture

DATA_INFLOW -> **Router** -> TCP/NDJSON -> **Parser** -> XML spool -> **Forwarder**

- **Router**: file/TCP ingestion, stable-file detection, hashing, duplicate protection, routing, retry, persistent lifecycle state.
- **Parser**: SAIS/MSIS/LRIT/VATMS/NAIS parsing, AIS decoding, normalization, validation, positional spoofing detection, AIS/track state, WRS/PANS/NSC enrichment, fallback/provenance, XML generation and atomic XML spooling.
- **Forwarder**: XML spool monitoring, persistent delivery state, retry and filesystem/SFTP delivery.
- **RocksDB**: the only runtime database engine. Router state, parser AIS state, parser track/reference state, WRS/PANS/NSC and forwarder delivery state all use RocksDB.
- **SQLite** exists only inside the one-time legacy migration utility to read old `.db` files.

## Start all three services

From the repository root:

```bash
python3 -m pip install -r router/requirements.txt
python3 -m pip install -r parser/requirements.txt
python3 -m pip install -r forwarder/requirements.txt

./scripts/start_validation.sh
```

The script starts Forwarder, Parser and Router as separate processes and connects them through ports 8080/8081/8082 and parser ports 10001-10005.

## Input folders

Put source files under:

```text
DATA_INFLOW/
  SAIS_IOR/
  SAIS_GLOBAL/
  MSIS/
  LRIT/
```

VATMS East/West and NAIS TCP inputs are disabled by default for a clean local run; enable and configure them in `router/config/sources.yaml` when the actual feeds are available.

## Reference databases

The runtime expects migrated RocksDB stores at:

```text
parser/reference/wrs
parser/reference/pans
parser/reference/nsc
```

The reference resolver preserves the old WRS/PANS/NSC lookup logic, match methods, field-level enrichment, fallback/provenance and bounded resolution cache. The RocksDB reference adapter supports the SQL query shapes used by that resolver without running SQLite.

## Migrating an existing Validation installation

If the old `validation-docker` repository is next to this repository:

```bash
./migration/run_migration.sh
```

Or set:

```bash
export LEGACY_VALIDATION_HOME=/path/to/old/validation-docker
./migration/run_migration.sh
```

The migration covers all seven legacy SQLite stores:

1. WRS
2. PANS
3. NSC
4. Router file lifecycle state
5. Parser AIS state
6. Parser track/reference state
7. Forwarder delivery state

The migration writes to the exact runtime RocksDB locations and emits row-count manifests. Do not start the services while a migration is running.

## Smoke/preflight

```bash
./scripts/preflight.sh
```

After the services are running:

```bash
python3 scripts/smoke_test.py
```

Logs are written under `logs/`.

## Important deployment note

Production reference DB binaries and historical runtime state are not stored in Git. The repository contains the migration and runtime logic; the actual WRS/PANS/NSC data must be supplied as the migrated RocksDB stores on the deployment machine.
