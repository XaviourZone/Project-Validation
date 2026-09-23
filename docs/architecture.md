# Project-Validation Architecture

Router, Parser, and Forwarder are independently executable applications.

## Data flow

INPUT SOURCES
-> ROUTER
-> PARSER INPUT SPOOL
-> PARSER
   -> Decode
   -> Normalize
   -> Validate
   -> Correlate
   -> WRS RocksDB
   -> PANS RocksDB
   -> NSC RocksDB
   -> Fusion
   -> XML
-> XML SPOOL
-> FORWARDER
-> DESTINATION

Reference databases are Parser-owned runtime assets, not separate services.

Router performs input discovery and routing only.
Parser owns parsing, decoding, normalization, validation, correlation, enrichment, fusion and XML generation.
Forwarder owns output delivery and retry.

Runtime processing must not use direct Python calls between the three services.
