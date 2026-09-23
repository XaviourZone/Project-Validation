# Project-Validation architecture

Project-Validation has three independent runtime services:

    DATA SOURCES -> ROUTER -> PARSER -> XML SPOOL -> FORWARDER -> DOWNSTREAM

Router owns ingestion and routing. Parser owns parsing, decoding, normalization, validation, correlation, reference enrichment, fusion and XML generation. Forwarder owns downstream delivery.

## Storage rule

**RocksDB is the only runtime database engine. SQLite is not part of the target runtime.**

Persistent stores are isolated by responsibility:

- Router state: router/state
- Parser AIS state: parser/state/ais
- Parser track/reference state: parser/state/track
- Parser WRS reference: parser/reference/wrs
- Parser PANS reference: parser/reference/pans
- Parser NSC reference: parser/reference/nsc
- Forwarder delivery state: forwarder/state/delivery

The one-time legacy migration utility may read SQLite source files solely to convert them to RocksDB. Services do not depend on SQLite.
