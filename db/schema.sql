-- Idempotent: safe to run repeatedly.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Postgres has no Latvian stemmer. Until we add one (e.g. Hunspell lv_LV), use
-- 'simple' plus unaccent so queries typed without diacritics still match.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'lv') THEN
        CREATE TEXT SEARCH CONFIGURATION lv (COPY = simple);
        ALTER TEXT SEARCH CONFIGURATION lv
            ALTER MAPPING FOR hword, hword_part, word WITH unaccent, simple;
    END IF;
END
$$;

-- One row per published document, straight from the data.gov.lv CSV.
CREATE TABLE IF NOT EXISTS decisions (
    id                 uuid PRIMARY KEY,         -- MaterialFileId
    court              text NOT NULL,
    court_department   text,
    ecli               text,
    case_number        text,
    application_number text,
    process_type       text,
    process_subtype    text,
    material_type      text,
    registration_date  date,
    status             text,
    court_instance     text,
    download_url       text NOT NULL
);

CREATE INDEX IF NOT EXISTS decisions_case_number_idx ON decisions (case_number);
CREATE INDEX IF NOT EXISTS decisions_application_number_idx ON decisions (application_number);
CREATE INDEX IF NOT EXISTS decisions_ecli_idx ON decisions (ecli);
CREATE INDEX IF NOT EXISTS decisions_registration_date_idx ON decisions (registration_date);
CREATE INDEX IF NOT EXISTS decisions_process_type_idx ON decisions (process_type);

-- Extracted text for decisions whose PDF has been downloaded.
CREATE TABLE IF NOT EXISTS documents (
    decision_id uuid PRIMARY KEY REFERENCES decisions (id) ON DELETE CASCADE,
    body        text NOT NULL,
    tsv         tsvector GENERATED ALWAYS AS (to_tsvector('lv', body)) STORED
);

CREATE INDEX IF NOT EXISTS documents_tsv_idx ON documents USING gin (tsv);
