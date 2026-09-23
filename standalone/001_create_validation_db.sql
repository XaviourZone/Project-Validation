-- Run this script with psql against the PostgreSQL maintenance database.
-- It creates the application database and the minimal Validation schema.
CREATE DATABASE validation;
\connect validation;
CREATE SCHEMA IF NOT EXISTS validation;
CREATE TABLE IF NOT EXISTS validation.reference_record (
 id BIGSERIAL PRIMARY KEY,
 dataset_code TEXT NOT NULL CHECK (dataset_code IN ('WRS','PANS','NSC','UNLOCODE')),
 logical_table TEXT NOT NULL,
 source_file TEXT,
 source_row BIGINT,
 vessel_id TEXT,
 mmsi BIGINT,
 imo BIGINT,
 callsign TEXT,
 vessel_name TEXT,
 record_hash TEXT NOT NULL,
 payload JSONB NOT NULL,
 loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS reference_record_dataset_mmsi_idx ON validation.reference_record(dataset_code,mmsi);
CREATE INDEX IF NOT EXISTS reference_record_dataset_imo_idx ON validation.reference_record(dataset_code,imo);
CREATE INDEX IF NOT EXISTS reference_record_dataset_vessel_idx ON validation.reference_record(dataset_code,vessel_id);
CREATE INDEX IF NOT EXISTS reference_record_dataset_hash_idx ON validation.reference_record(dataset_code,record_hash);
CREATE TABLE IF NOT EXISTS validation.reference_status (
 dataset_code TEXT PRIMARY KEY CHECK (dataset_code IN ('WRS','PANS','NSC','UNLOCODE')),
 source_folder TEXT,
 status TEXT NOT NULL DEFAULT 'NOT_READY',
 record_count BIGINT NOT NULL DEFAULT 0,
 file_count INTEGER NOT NULL DEFAULT 0,
 last_update TIMESTAMPTZ,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO validation.reference_status(dataset_code) VALUES ('WRS'),('PANS'),('NSC'),('UNLOCODE') ON CONFLICT (dataset_code) DO NOTHING;
CREATE TABLE IF NOT EXISTS validation.live_data (
 source_id TEXT PRIMARY KEY,
 unlocode TEXT,
 current_data JSONB NOT NULL DEFAULT '{}'::jsonb,
 xml_destination TEXT,
 last_xml_update TIMESTAMPTZ,
 last_seen TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS live_data_unlocode_idx ON validation.live_data(unlocode);
CREATE INDEX IF NOT EXISTS live_data_last_seen_idx ON validation.live_data(last_seen DESC);
