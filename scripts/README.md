# Standalone Validation scripts

This directory is the operator-facing runtime entrypoint.

## Feed programs

- SAIS_IOR.py
- SAIS_GLOBAL.py
- MSIS.py
- LRIT.py
- VATMS_EAST.py
- VATMS_WEST.py
- NAIS.py

Each file has its editable SOURCE_ID, INPUT, ROUTER, DATABASE and DESTINATION configuration at the top and runs independently.

## Database / console

database_manager.py is the single database manager and local browser console. It starts the portable PostgreSQL runtime, creates the schema, imports WRS/PANS/NSC/UNLOCODE reference data and controls the seven feed processes.

PostgreSQL contains only:
- WRS reference data
- PANS reference data
- NSC reference data
- UN/LOCODE reference data
- current live vessel data

Runtime status is stored locally in runtime/status/*.json.

## Start

python scripts/database_manager.py

Then open http://127.0.0.1:8080

The PostgreSQL binaries are deployment artifacts under postgres/portable/. Do not copy postgres/data between Windows and Linux.
