CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.schema_migrations (
    version integer PRIMARY KEY CHECK (version BETWEEN 0 AND 999),
    name text NOT NULL UNIQUE,
    checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
    apply_mode text NOT NULL CHECK (apply_mode IN ('executed', 'baselined')),
    component_versions jsonb NOT NULL DEFAULT '{}'::jsonb,
    manifest_hash text NOT NULL CHECK (manifest_hash ~ '^[0-9a-f]{64}$'),
    application_schema_signature text
        CHECK (application_schema_signature IS NULL OR application_schema_signature ~ '^[0-9a-f]{64}$'),
    checkpoint_schema_signature text
        CHECK (checkpoint_schema_signature IS NULL OR checkpoint_schema_signature ~ '^[0-9a-f]{64}$'),
    applied_at timestamptz NOT NULL DEFAULT now()
);
