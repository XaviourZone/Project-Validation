CREATE TABLE IF NOT EXISTS source (
    source_id INTEGER PRIMARY KEY,
    source_name TEXT NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS field_mapping (
    id BIGSERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES source(source_id),
    input_field TEXT NOT NULL,
    target_field TEXT NOT NULL,
    transformation TEXT,
    priority INTEGER NOT NULL DEFAULT 1,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE(source_id, input_field, target_field)
);

CREATE TABLE IF NOT EXISTS destination_mapping (
    id BIGSERIAL PRIMARY KEY,
    source_code TEXT NOT NULL,
    destination_code TEXT,
    destination_name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(source_code, destination_code, destination_name)
);

CREATE TABLE IF NOT EXISTS unlocode (
    code TEXT PRIMARY KEY,
    country_code TEXT,
    location_code TEXT,
    name TEXT NOT NULL,
    subdivision TEXT,
    status TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reference_rows (
    source_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    row_key TEXT NOT NULL,
    data JSONB NOT NULL,
    source_file TEXT,
    source_hash TEXT,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(source_name, table_name, row_key)
);

CREATE TABLE IF NOT EXISTS reference_row_history (
    history_id BIGSERIAL PRIMARY KEY,
    source_name TEXT NOT NULL,
    table_name TEXT NOT NULL,
    row_key TEXT NOT NULL,
    data JSONB NOT NULL,
    source_file TEXT,
    source_hash TEXT,
    version_time TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ingest_file (
    source_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    records INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_attempt TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(source_name, file_hash)
);

CREATE TABLE IF NOT EXISTS pans_pending (
    file_path TEXT PRIMARY KEY,
    file_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    last_error TEXT,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_attempt TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_reference_rows_lookup
    ON reference_rows(source_name, table_name);

CREATE INDEX IF NOT EXISTS ix_reference_rows_data
    ON reference_rows USING GIN(data);

CREATE INDEX IF NOT EXISTS ix_history_lookup
    ON reference_row_history(source_name, table_name, row_key);

INSERT INTO source(source_id,source_name,description) VALUES
(1,'SAIS_IOR','Raw NMEA AIS - Indian Ocean Region'),
(2,'SAIS_GLOBAL','Raw NMEA AIS - Global'),
(3,'MSIS','Already-decoded AIS'),
(4,'LRIT','LRIT vessel information'),
(5,'VATMS_EAST','VATMS East NMEA/network feed'),
(6,'VATMS_WEST','VATMS West Transas/network feed'),
(7,'NAIS','National AIS network feed')
ON CONFLICT(source_id) DO UPDATE SET source_name=EXCLUDED.source_name, description=EXCLUDED.description, updated_at=now();

CREATE TABLE IF NOT EXISTS vessel_state (
    mmsi BIGINT PRIMARY KEY,
    values JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_timestamp TIMESTAMPTZ,
    last_source TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vessel_state_history (
    id BIGSERIAL PRIMARY KEY,
    mmsi BIGINT NOT NULL,
    values JSONB NOT NULL,
    event_timestamp TIMESTAMPTZ,
    source TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_vessel_state_source ON vessel_state(last_source);
