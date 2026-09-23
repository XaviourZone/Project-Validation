# Validation — Standalone PostgreSQL Architecture

This branch implements the finalized architecture:

- one independent Python program per feed:
  - `SAIS_IOR.py`
  - `SAIS_GLOBAL.py`
  - `MSIS.py`
  - `LRIT.py`
  - `VATMS_EAST.py`
  - `VATMS_WEST.py`
  - `NAIS.py`
- one PostgreSQL database managed by `db/db_manager.py`
- PANS is monitored continuously by the DB manager
- WRS and NSC are manually imported/upserted
- reference history is retained
- every feed writes one canonical XTrack XML document per accepted record
- the output folder is configurable at the top of every feed script
- no Internet/cloud service is required at runtime

The feed scripts contain their own parsing, normalization, validation, correlation, enrichment, fusion and XML-generation logic. The only shared runtime module is the PostgreSQL/file/TCP I/O helper; it contains no feed business rules.

## Runtime layout

```
standalone/
  db/
    schema.sql
    db_manager.py
    START_DB.sh
    START_DB.bat
    config.json
  feeds/
    _runtime.py
    SAIS_IOR.py
    SAIS_GLOBAL.py
    MSIS.py
    LRIT.py
    VATMS_EAST.py
    VATMS_WEST.py
    NAIS.py
  requirements.txt
  offline/
    download_wheels.py
```

## PostgreSQL

Install PostgreSQL and set the application password in local `db/config.json`. Run `python3 db/bootstrap_db.py` once to create the application role/database, then run `psql -h 127.0.0.1 -U validation -d validation -f db/schema.sql` and `python3 db/seed_defaults.py`.

Default local connection:

```
host=127.0.0.1
port=5432
database=validation
user=validation
password=<operator configured password>
```

Do not commit a real password. Put it in the local `standalone/db/config.json`.

## Offline Python installation

On an Internet-connected machine:

```
python offline/download_wheels.py --platform manylinux_2_17_x86_64 --python-version 3.13
```

Copy `standalone/offline/wheels` to the offline Ubuntu host and install:

```
python3 -m pip install --no-index --find-links standalone/offline/wheels -r standalone/requirements.txt
```

The application does not download anything at runtime.

## Feed test

Set `INPUT_MODE="FOLDER"`, `INPUT_FOLDER`, and `OUTPUT_FOLDER` at the top of the feed script.

Then:

```
python3 standalone/feeds/SAIS_IOR.py
```

Every accepted record produces a separate XML file in the configured output folder.

For network feeds set `INPUT_MODE="TCP"`, `TCP_HOST`, and `TCP_PORT`.

## Important migration note

The older Router/Parser/Forwarder tree remains in this branch during migration so the new implementation can be validated without destroying the previously accepted runtime. It is not used by the standalone feed programs.
