# Project-Validation

Three-service offline maritime/AIS processing architecture:

- `router/` — input discovery, stable-file handling, routing and Router UI
- `parser/` — parsing, decoding, normalization, validation, correlation, enrichment, WRS/PANS/NSC lookups, fusion and XML generation
- `forwarder/` — XML/output delivery, retry and Forwarder UI
- `reference/` — runtime reference-data build/migration assets for RocksDB
- `shared/` — minimal shared contracts/utilities
- `docs/` — architecture and migration documentation

The repository is intentionally initialized as a clean target structure. The existing Validation implementation should be migrated into these boundaries without changing business rules or XML mappings.
