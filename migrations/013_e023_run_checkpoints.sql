-- Persistent run checkpoints for the iteration loop (E-023 contract).
-- A mid-loop crash/restart leaves a `running` checkpoint that `resume_run`
-- re-authorizes and continues. The checkpoint is the ONLY recovery signal; the
-- Metadata DB is the source of truth (build plan §10.10 / M7 §3623).
-- Applied by MetadataStore.apply_migrations(); safe to re-apply.

CREATE TABLE IF NOT EXISTS run_checkpoints (
    run_id          TEXT PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    corpus_id       TEXT NOT NULL,
    query           TEXT NOT NULL,
    policy_version  TEXT NOT NULL,
    status          TEXT NOT NULL,
    round_index     INTEGER NOT NULL,
    state_json      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    expires_at      TEXT
);
