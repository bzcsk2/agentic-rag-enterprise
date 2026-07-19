-- Reconciler support (E-022, build plan §10.10)
-- Applied by MetadataStore.apply_migrations() at construction time.

CREATE TABLE IF NOT EXISTS reconciler_leases (
    corpus_id   TEXT PRIMARY KEY,
    owner       TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reconciliation_runs (
    run_id        TEXT PRIMARY KEY,
    corpus_id     TEXT NOT NULL,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    finding_count INTEGER NOT NULL DEFAULT 0,
    mutated       INTEGER NOT NULL DEFAULT 0,
    dry_run       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reconciliation_findings (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id           TEXT NOT NULL,
    kind             TEXT NOT NULL,
    corpus_id        TEXT NOT NULL,
    tenant_id        TEXT,
    document_id      TEXT,
    document_version TEXT,
    detail           TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_recon_findings_run ON reconciliation_findings(run_id);
