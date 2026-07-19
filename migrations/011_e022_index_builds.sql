-- Index migration tracking (E-022, build plan §10.8)
-- Applied by MetadataStore.apply_migrations() at construction time.

CREATE TABLE IF NOT EXISTS index_builds (
    build_id           TEXT PRIMARY KEY,
    corpus_id          TEXT NOT NULL,
    collection_name    TEXT NOT NULL,
    embedding_version  TEXT NOT NULL,
    chunking_version   TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'building',
    previous_collection TEXT,
    started_at         TEXT NOT NULL,
    finished_at       TEXT
);

CREATE INDEX IF NOT EXISTS idx_index_builds_corpus ON index_builds(corpus_id);
