# Migration

The repository currently starts from an empty GitHub baseline.

When the existing Validation implementation is supplied/mounted:
1. Inventory files and entry points.
2. Map responsibility to router/parser/forwarder.
3. Preserve business rules and XML mappings.
4. Classify SQLite databases.
5. Migrate only high-frequency reference data to RocksDB.
6. Verify WRS/PANS/NSC counts and lookup equivalence.
7. Run unit, integration and end-to-end tests.
8. Benchmark the lookup path.
