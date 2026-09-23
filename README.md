# Validation — Final Standalone Architecture

The active target architecture is now independent feed programs plus one shared PostgreSQL reference/configuration database.

## Feed programs

SAIS_IOR.py — folder, raw NMEA AIS
SAIS_GLOBAL.py — folder, raw NMEA AIS
MSIS.py — folder, already-decoded CSV
LRIT.py — folder, LRIT CSV
VATMS_EAST.py — TCP, VATMS/NMEA
VATMS_WEST.py — TCP, Transas TMVTD/NMEA
NAIS.py — TCP, ABVDM/ABVDO NMEA

Each program has its own operator-editable settings and its own parser, normalization, validation, correlation, enrichment, fusion and XML generation path.

The only shared runtime module is standalone/feeds/_runtime.py. It contains PostgreSQL/file/TCP plumbing only and no feed business rules.

## PostgreSQL DB manager

standalone/db/db_manager.py initializes the schema, imports WRS and NSC, continuously watches PANS XML, retries pending PANS files, and exposes a local web console for status/search/import operations.

Reference updates are UPSERTs. Replaced current values are retained in reference_row_history; data is not destructively deleted.

The database also stores source IDs, field mappings, destination mappings, UN/LOCODE, ingest state, persistent vessel state and state history.

## Offline deployment

On an Internet-connected staging machine:

    python3 standalone/offline/download_wheels.py

Move standalone/offline/wheels to the offline Ubuntu machine and install:

    python3 -m pip install --no-index --find-links standalone/offline/wheels -r standalone/requirements.txt

Install PostgreSQL separately, create the validation database/role, run standalone/db/schema.sql, configure standalone/db/config.json, then start standalone/db/START_DB.sh.

## Test method

Configure one feed at a time with an input folder or TCP endpoint and an XML output folder. Start PostgreSQL/DB manager, run the feed, and inspect the generated XML files. Test malformed input, missing identity, duplicate files, missing reference rows, database restart and process restart.

The older Router/Parser/Forwarder implementation remains during migration so the new runtime can be compared with the previously accepted real-data baseline before the old implementation is removed.
