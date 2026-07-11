-- E-008.1 migration: per-job revision baseline, replaced-version tracking, manifest.
-- Build plan §10.10 #2/#8 (base_revision CAS), #2/#8 (previous_active_version),
-- §10.9 (manifest). Applied by the MetadataStore migrator (idempotent per version).

ALTER TABLE ingestion_jobs ADD COLUMN base_revision INTEGER NOT NULL DEFAULT 0;
ALTER TABLE ingestion_jobs ADD COLUMN previous_active_version TEXT;
ALTER TABLE ingestion_jobs ADD COLUMN manifest TEXT;
