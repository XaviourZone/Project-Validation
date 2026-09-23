# Validation Standalone Runtime

Standalone offline runtime for the Validation maritime/AIS pipeline.

Flow: INPUT -> ROUTER -> SOURCE PARSER -> NORMALIZATION/VALIDATION -> CORRELATION -> WRS/PANS/NSC -> UN/LOCODE -> XTrack XML -> DESTINATION.

PostgreSQL contains only WRS, PANS, NSC, UN/LOCODE reference data and the current live data needed for monitoring. Runtime process status is local JSON under runtime/status; parser history, XML history, logs, heartbeats, offsets and other application state are not stored in PostgreSQL.

## Source programs
SAIS_IOR.py, SAIS_GLOBAL.py, MSIS.py, LRIT.py, VATMS_EAST.py, VATMS_WEST.py, NAIS.py.
Each program has an editable configuration block at the top for its input, router, PostgreSQL and XML destination settings.

## Existing logic preserved
The source parsers, normalization, validation, correlation, field-specific WRS/PANS/NSC fallbacks, UN/LOCODE resolution and Athena XTrack 41-field XML contract are carried forward from Project-Validation. Missing values are omitted rather than fabricated.
