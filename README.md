# Project-Validation

Offline maritime/AIS validation pipeline with four independent processes that cooperate over local interfaces.

## Runtime architecture

DATA_INFLOW -> **Router** -> TCP/NDJSON -> **Parser** -> XML spool -> **Forwarder**

- **Router**: file/TCP ingestion, stable-file detection, hashing, duplicate protection, routing, retry and persistent lifecycle state.
- **Parser**: SAIS/MSIS/LRIT/VATMS/NAIS parsing, AIS decoding, normalization, validation, positional spoofing detection, AIS/track state, WRS/PANS/NSC enrichment, fallback/provenance, XML generation and atomic XML spooling.
- **Forwarder**: XML spool monitoring, persistent delivery state, retry and filesystem/SFTP delivery.
- **Operator Console**: local control/configuration UI. Router, Parser and Forwarder remain independent OS processes; the launcher records their PIDs so the Console can safely monitor, start, stop and restart them without opening additional terminals.
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

The Console can load and **update**:
- **WRS** from an operator-selected folder containing `Datasets/` and either `Decode/` or `Decode files/`. Every CSV currently present in those folders is read when **LOAD/UPDATE ROCKSDB** is pressed. The existing RocksDB reference store is rebuilt from the current source contents and atomically replaced, so updated WRS CSVs are picked up on the next update.
- **PANS** from an operator-selected folder. XML files are discovered recursively from that folder using the established VesselProfile/VoyageRegistration/VesselCallNumber/BerthManagement mappings.
- **NSC** from an operator-selected folder containing both `NSC_EAST*.csv` and `NSC_WEST*.csv` data (or EAST/WEST subfolders). Both regional datasets are loaded into `nsc_vessels` with `SOURCE_REGION=EAST/WEST`. The Console validates that both regions are present before loading.

Reference updates follow this operator workflow:

**Mapped source folder → Validate → Stop Parser → Load/Update RocksDB → Start Parser → new reference data used by enrichment.**

The **UPDATE ROCKSDB** action automates this sequence: it validates the selected source, safely stops the running Parser using the launcher PID, rebuilds the selected reference store from the current source files, atomically replaces the store, and starts Parser again. If Parser was already stopped, the update leaves it stopped.

- **WRS:** select one root folder containing `Datasets/` and either `Decode/` or `Decode files/`. Every current CSV below those folders is read on each update.
- **PANS:** select a root folder; XML files are discovered recursively and loaded using the established PANS root mappings.
- **NSC:** select a root folder containing both `NSC_EAST*.csv` and `NSC_WEST*.csv`, or EAST/WEST subfolders. Both regions are required and are loaded with `SOURCE_REGION=EAST/WEST`.

No manual deletion of the existing RocksDB reference store is required.
