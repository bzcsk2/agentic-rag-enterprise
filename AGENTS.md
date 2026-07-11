# AGENTS.md — Agentic RAG Enterprise

## Implementation Spec
`docs/agentic-rag-enterprise-build-plan.md`

## Current Milestone & Issue
- Milestone: **M1** — Secure single-corpus data vertical slice
- Issue: **E-007** — Port parent-child chunking + hybrid retrieval from upstream (algorithm only, enterprise security envelope)
- Prior issue **E-006.1** — CLOSED at `807aa0c` (deprecated flag in PEP, real cross-tenant tests, Qdrant PDP/PEP equivalence).

## Fixed Paths
```bash
UPSTREAM_REPO=/vol4/Agent/agentic-rag-for-dummies
TARGET_REPO=/vol4/Agent/agentic-rag-enterprise
```

## Fixed Commits (M1 baseline)
- Target: `3748b33ffa37a0f977d9ba448e6d760a639b5eba` (main)
- Upstream: `8b3e5ff0619f7ede593d728e4a8b459fbbec9b08` (main, tag v2.3)

## Permanent Rules (all milestones)
1. **DO NOT modify upstream** (`/vol4/Agent/agentic-rag-for-dummies/`).
2. Target uses `src/agentic_rag_enterprise/` package layout.
3. `pyproject.toml` is the single source of truth for dependencies.
4. Do not create empty code directories.
5. Keep existing working tree changes; do not reset, checkout, or overwrite.

## E-005 Allowed Changes (M1 only) — completed
- `src/agentic_rag_enterprise/domain/` — create or modify domain models
- `migrations/` — create or modify migration scaffolding
- `tests/test_domain_models.py` — create or modify
- `AGENTS.md` — update
- Do not modify existing modules under `src/agentic_rag_enterprise/{agents,graph,retrieval,api,evals,observability,ingestion,security,config,schemas,providers}`.
- No upstream modifications. No push, no PR creation.

## E-006 Allowed Changes (M1 only)
- `src/agentic_rag_enterprise/security/` — create or modify policy truth table, PEP filter, authorization
- `src/agentic_rag_enterprise/domain/security.py` — may be read; SecurityContext already matches spec §7.5
- `tests/security/` — create authorization tests (truth table, corpus discoverability, PEP filter)
- `AGENTS.md` — update
- Keep `security/policy.py:AccessPolicy.can_access(user_id, corpus)` shim so the M0 baseline
  characterization tests in `tests/baseline/test_retrieval_baseline.py` stay green.
- No upstream modifications. No push, no PR creation.

## E-006.1 Allowed Changes (M1 only) — CLOSED at `807aa0c`
- `src/agentic_rag_enterprise/security/filter.py` — add `deprecated == false` to `build_access_filter`
  and to `resource_passes_filter`; this makes the PEP filter structurally express the active,
  non-deprecated invariant that `migrations/001_initial_schema.sql` intends for rows. (Note: the
  migration does **not** add a runtime DB CHECK — the PEP filter is the enforcement point, not the DDL.)
- `tests/security/test_authorization.py` — replace the fake same-tenant "cross-tenant" rows with
  real cross-tenant cases (ctx tenant != acl tenant), add `deprecated` unit test, bump `must` count.
- `tests/integration/test_qdrant_authorization.py` — new; real in-memory Qdrant collection proving
  PDP (`evaluate_access`) == Qdrant Filter (`build_access_filter`) over the ACL matrix.
- `AGENTS.md` — update issue + record E-007 constraint.
- No upstream modifications. No push, no PR creation.

## E-007 Issue Contract (M1 only) — IN PROGRESS
Port parent-child chunking + hybrid retrieval from upstream (`agentic-rag-for-dummies`, tag v2.3,
read-only). Port **algorithms only**; never upstream trust boundaries.

### Allowed paths
- `src/agentic_rag_enterprise/ingestion/` — port parent-child chunking algorithm
  (heading-aware split, merge-small / split-large parents, rebalance, recursive child split).
  Parent/child IDs MUST be content-addressed + tenant-scoped (`sha256`, NOT filename-derived);
  chunks MUST carry provenance (`document_id`, `tenant_id`, `corpus_id`, `section_path`,
  `document_version`).
- `src/agentic_rag_enterprise/retrieval/` — hybrid retrieval, parent reader (second-auth),
  corpus-discoverability gate.
- `src/agentic_rag_enterprise/storage/` — new Qdrant hybrid vector store + in-memory parent store.
- `src/agentic_rag_enterprise/security/` — may extend (e.g. `can_discover_corpus` /
  `allowed_corpus_ids`); the PEP/PDP truth table stays `build_access_filter` / `evaluate_access`
  / `resource_passes_filter`.
- `tests/{unit,integration,security,fixtures}/` — new tests + shared fixtures.
- `pyproject.toml`, `uv.lock` — dependencies (`langchain-text-splitters`, `fastembed`;
  `qdrant-client` already present).
- `AGENTS.md`, `docs/upstream-capability-map.md`.

### Forbidden
- No upstream modifications. No push, no PR creation.
- MUST use `evaluate_access` / `build_access_filter` / `resource_passes_filter`; MUST NOT use
  `AccessPolicy.can_access` on any retrieval path.
- No filename-derived parent IDs; no filter-less retrieval.
- Do **NOT** add encoders/config to `config.py` / `Settings` — inject them (the E-007 contract
  permits `ingestion/`, `retrieval/`, `storage/`, `security/`, `tests/...`, pyproject only;
  `config.py` and `domain/` are out of scope).
- Do not modify existing modules outside the allowed paths.

### Security requirements
1. **Corpus discoverability gate** — every retrieval entry point MUST validate
   `can_discover_corpus` / `allowed_corpus_ids` (tenant match + enabled + searchable +
   `allowed_corpus_ids`) BEFORE `build_access_filter`, because the filter does not read
   `allowed_corpus_ids`. Fail-closed (`CorpusNotDiscoverableError`).
2. **PEP/PDP are the filter functions** — `build_access_filter` (Qdrant `Filter`) and
   `evaluate_access` (PDP) are authoritative; empty ACL lists (`groups`, `allowed_security_levels`)
   fail-closed via a sentinel that matches nothing.
3. **Parent second authorization** — `ParentReader` is the ONLY authorized parent accessor; it
   re-verifies identity (tenant/corpus/document/version), lifecycle (active, not deprecated),
   ACL-metadata consistency, and `resource_passes_filter`. Fail-closed (`ParentAuthorizationError`).
4. **`SecurityContext` required** on every retrieval path.
5. **M0 baseline regression** (`tests/baseline/test_retrieval_baseline.py`) MUST stay green;
   `SimpleChunker` + mock `Retriever` retained as adapters.

### Acceptance tests
- `tests/unit/test_parent_child_chunker.py`
- `tests/integration/test_qdrant_hybrid_retrieval.py`
- `tests/security/test_parent_reader.py`
- `tests/integration/test_e007_end_to_end.py`
- `tests/baseline/` MUST remain green.
- `ruff`, `mypy src/agentic_rag_enterprise` clean.

## Standard Checks
```bash
# Before starting a task
cd $TARGET_REPO
git status --short
git branch --show-current
git rev-parse HEAD

cd $UPSTREAM_REPO
git status --short
git rev-parse HEAD

# After completing a task
cd $TARGET_REPO
git diff --check
git status --short
```
