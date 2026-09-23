# Project-Validation

Offline maritime/AIS validation pipeline with four independent processes that cooperate over local interfaces.

## Runtime architecture

DATA_INFLOW -> **Router** -> TCP/NDJSON -> **Parser** -> XML spool -> **Forwarder**

- **Router**: file/TCP ingestion, stable-file detection, hashing, duplicate protection, routing, retry and persistent lifecycle state.
- **Parser**: SAIS/MSIS/LRIT/VATMS/NAIS parsing, AIS decoding, normalization, validation, positional spoofing detection, AIS/track state, WRS/PANS/NSC enrichment, fallback/provenance, XML generation and atomic XML spooling.
- **Forwarder**: XML spool monitoring, persistent delivery state, retry and filesystem/SFTP delivery.
- **Operator Console**: local control/configuration UI. It does not own the other services.
- **RocksDB**: the only runtime database engine. SQLite is used only by the one-time legacy migration utility.

## Start the complete system

Linux/RHEL:
\`\`\`bash
./scripts/start_all.sh
\`\`\`

Windows:
\`\`\`bat
scripts\\start_all.bat
\`\`\`

The four processes start simultaneously and remain independent. Console: \`http://127.0.0.1:8080\`, Router: \`http://127.0.0.1:18080\`, Parser: \`http://127.0.0.1:18081\`, Forwarder: \`http://127.0.0.1:18082\`.

\`scripts/start_validation.sh\` and \`scripts/start_validation.bat\` are compatibility aliases to the same all-services launcher.

## First end-to-end test

1. Install the offline wheels from the three service requirement files.
2. Start the system with \`./scripts/start_all.sh\`.
3. Open the Console.
4. In **Reference Database**, select the WRS source folder. The WRS source must contain \`Datasets\` and either \`Decode\` or \`Decode files\`.
5. Save the source and **stop Parser**.
6. Press **LOAD ROCKSDB** for WRS. The console builds a fresh RocksDB store and replaces \`parser/reference/wrs\` only after the import succeeds.
7. Start Parser again. This guarantees the parser opens the newly built store with a fresh reference-resolution cache.
8. In **Router → SAIS_IOR**, select the real source folder, enable it, ensure the file pattern includes \`*.csv\`, then APPLY and restart Router.
9. Put an SAIS CSV/NMEA file into that source folder.
10. Watch Router and Parser status/logs. The Router reads the complete file, sends one envelope to the SAIS endpoint, and waits for parser ACK.
11. Parser SAIS decodes the NMEA records, then normalizes, validates, correlates/enriches against WRS/PANS/NSC, generates one XTrack XML document per successful record, validates downstream compatibility, and writes XML files to \`forwarder/spool/pending\`.
12. Forwarder sees those XML files. Its configured D-DIODE destination is disabled by default, so the XML remains available in the pending spool for inspection.

### What to inspect

\`\`\`bash
tail -f logs/router.log
tail -f logs/parser.log
tail -f logs/forwarder.log
ls -lh forwarder/spool/pending/
\`\`\`

The Console Reference card shows loaded file/row counts from \`REFERENCE_MANIFEST.json\`.

## Input folders

Default file sources:

\`\`\`text
DATA_INFLOW/
  SAIS_IOR/
  SAIS_GLOBAL/
  MSIS/
  LRIT/
\`\`\`

VATMS East/West and NAIS are TCP sources and are disabled by default.

## Reference databases

Runtime stores:

\`\`\`text
parser/reference/wrs
parser/reference/pans
parser/reference/nsc
\`\`\`

The Console can load:
- WRS CSVs from Datasets + Decode/Decode files.
- PANS XML files using the established VesselProfile/VoyageRegistration/VesselCallNumber/BerthManagement mappings.
- NSC CSV files into \`nsc_vessels\`, preserving EAST/WEST source-region information when the folder path contains those names.

Reference loading is intentionally blocked while Parser is reachable. Stop Parser first, load the store, then start Parser. This prevents replacing an open RocksDB directory and prevents stale in-process reference-cache results.

## Legacy migration

\`\`\`bash
./migration/run_migration.sh
\`\`\`

SQLite remains restricted to this one-time migration utility.

## Preflight

\`\`\`bash
./scripts/preflight.sh
\`\`\`


## Offline dependency bundle

The repository uses a local virtual environment at `.venv` and a local wheelhouse at `offline/wheels`.

### Internet-connected preparation machine

Use the same OS, CPU architecture and Python major/minor version as the offline target:

```bash
python scripts/setup_dependencies.py --download
```

Windows:

```bat
py -3 scripts\setup_dependencies.py --download
```

This downloads the complete dependency set, including transitive dependencies, into `offline/wheels/`.

Copy the complete `offline/wheels` directory to the offline server. Do not rely on packages already installed on the preparation machine.

### Offline server

After copying the repository and `offline/wheels`:

```bash
./scripts/start_all.sh
```

Windows:

```bat
scripts\start_all.bat
```

The launcher automatically creates `.venv`, installs the required packages from `offline/wheels` using `--no-index`, and starts Router, Parser, Forwarder and Console using that same local Python environment.

No Internet is required after the wheelhouse has been prepared.

For installation without starting services:

```bash
python scripts/setup_dependencies.py --install
```

The RocksDB binding is the approved `amulet-rocksdb` package and exposes the Python `rocksdb` module used by the application. Its wheel is platform/Python-version specific, so the wheelhouse should be prepared for the same target environment. citeturn0search4turn1search0
