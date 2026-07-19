# Issue E-023 — Persistent checkpoint + re-authorization on resume

**Milestone:** M7 — Runtime hardening (`E-022` → `E-024`)
**Status:** contract open — implementation pending. Acceptance of this doc unlocks
`storage/checkpoint_store.py`, the `run_checkpoints` table + migration, the
resumable loop in `services/chat_service.py` (`answer_with_iteration` checkpointing
+ `resume_run`), and the `tests/.../test_e023_*` suites.
**Baseline:** `e06e5b1` (main HEAD; M6 CLOSED; M7 / E-022 CLOSED / ACCEPTED at
`cd4ddb2`; E-023 current).
**Build plan refs:** Milestone 7 (§3619 / §3621 / §3623 — exit gate: "重启恢复重新授权；ACL
收紧不因旧 Cache/Checkpoint 泄露"), §2988 (M7 restart before Research MVP must not
still rely on in-process-only state), §5080 (M7 / E-023 scope), §844 / §4195–§4201
(`storage/checkpoint.py` "新增，后期替换 InMemorySaver" — the persistent checkpoint
landing zone), §23.7 (quality-gate commands), §29.5 (`depends_on` / `in_scope` /
`deferred_to` rules).
**Depends on:** E-008 / E-008.x (idempotent ingestion + active-version protocol +
`MetadataStore` as control-plane source of truth), E-009 / E-010 (Parent Store
second-auth + logical delete / purge / ACL tightening), E-011 (evidence snapshot +
read-time re-authorization §12.8 — the canonical "re-auth against current ACL"
primitive this issue reuses), E-015 / E-016 (corpus registry discoverability truth),
E-019 / E-020 (the bounded, gap-driven iteration loop this issue checkpoints).
Reuses `storage/metadata_store.py` (source of truth + lease/reconciliation pattern),
`security/policy.py` (`evaluate_access`, `can_discover_corpus`, `ResourceAcl`),
`storage/evidence_store.py` (read-time re-auth shape), `retrieval/parent_reader.py`
(second-auth model). **No new storage engine is introduced** — local SQLite +
in-process/local Qdrant only (Postgres / Qdrant Server are M9).

---

## 1. Scope and non-goals

### In scope (restart-recovery hardening of the iteration loop)

- **Persistent run checkpoint** (`storage/checkpoint_store.py`): a `RunCheckpoint`
  captures the resumable state of an `answer_with_iteration` loop — the identity
  (`run_id`, `tenant_id`, `user_id`, `session_id`, `policy_version`), the request
  (`query`, `corpus_id`, `max_rounds`, `required_facts`), the accumulated evidence
  (`tuple[SnapshotEvidence, ...]`), and the loop trackers (`prior_queries`,
  `seen_text_hashes`, `seen_doc_versions`, `retrieval_calls`, `gap_rounds`,
  `final_reason`, `conflict_stop`, `coverage`, `final_report`, `round_index`). It is
  serialized to JSON and persisted in a new `run_checkpoints` table (migration
  `013_e023_run_checkpoints.sql`) on the **same** Metadata DB (the control-plane
  source of truth), via `MetadataStore` methods that mirror the existing
  lease/reconciliation pattern.
- **Checkpoint points**: `answer_with_iteration(..., run_id=...)` persists a
  checkpoint **after each completed round** (status `running`) and marks it
  `completed` when the loop finishes. A crash/restart between rounds leaves a
  `running` checkpoint that `resume_run` can pick up.
- **Resume + re-authorization** (`ChatService.resume_run(run_id, ctx)`):
  1. Load the checkpoint; verify `tenant_id` / `user_id` / `session_id` match the
     *current* `ctx` (cross-principal resume is refused — fail closed).
  2. Verify `policy_version` is unchanged (a different policy version means the
     stored authorization basis is stale → abort, fail closed).
  3. Re-validate corpus discoverability: `registry.get(corpus_id, ctx)` must
     succeed (`CorpusNotDiscoverableError` → abort).
  4. **Re-authorize every gathered Evidence against CURRENT metadata** (the core
     "ACL 收紧不因旧 Cache/Checkpoint 泄露" guarantee): for each evidence, resolve
     the current **active** document via `MetadataStore.get_active_document`; if it
     is absent / not `active` / `deprecated`, OR its `document_version` is no
     longer the active version, OR `evaluate_access(ctx, acl)` denies, OR the corpus
     is no longer discoverable → **drop that evidence** (fail closed). Surviving
     evidence rebuilds the loop trackers; any drop is recorded as a
     `resume_evidence_revoked` control-plane finding (reusing
     `MetadataStore.record_control_plane_finding`) for audit.
  5. Continue the loop from `round_index` using the **same** round body as the
     initial run, then synthesize. The final answer is **deterministic and identical**
     to an uninterrupted run *given the same re-auth outcome*.
- **Thin API surface** (`api/schemas.py` + `api/routes/chat.py`): `ChatRequest`
  gains optional `run_id: str | None = None` and `resume: bool = False` (backward
  compatible — defaults preserve the E-014 "query + corpus_id only" contract). The
  route calls `service.resume_run(run_id, ctx)` when `resume` is set, else
  `service.answer(..., run_id=run_id)`. The adapter stays thin and fail-closed.

### Deferred to sibling issues (do NOT pre-build)

- **E-024** — readiness + cancellation + backup/restore + runbooks. E-023 does
  **not** add `/health`/`/ready` endpoints, cancellation tokens, or backup/restore
  jobs. A checkpoint is a recovery primitive, not a cancellation token.
- **M9** — real Postgres, Qdrant Server, SSO, external connectors, online
  monitoring, canary. E-023 stays on local SQLite + in-process/local Qdrant; the
  checkpoint table is a single-process sqlite table (a restart that loses the temp
  sqlite file loses in-flight checkpoints — acceptable for the Internal MVP; the
  default container uses a temp file that survives the process while open).
- Distributed / multi-writer checkpoint leases, async job-based checkpointing, and
  cross-node resume are explicitly out of scope.

### Forbidden / non-goals

- **No LLM / NLP in the checkpoint or resume logic.** Both are deterministic and
  hermetic (the model is only ever invoked by the unchanged loop body / synthesis).
- **No new model download / external API in tests** — use the existing `fake`
  encoders, `FakeModel`/`_DevSynthesisModel`, and local Qdrant; tests must be fully
  hermetic.
- **No "预留接口" for E-024** — do not add unused cancellation/backup services,
  tables, or runtime branches "for later". Minimal type boundaries only, and only
  if exercised by a current test.
- **No change to the Planner core** (`planner/`, `executor.py`, `result.py`,
  `budget.py`, `tool_registry.py`) — frozen and out of scope for M7's E-023.
- **Checkpoint must never resurrect or leak**: re-auth-dropped evidence must never
  re-surface in the resumed answer, the synthesis prompt, or any finding detail.
- **Single-pass `answer` is not checkpointed** (one round; resume is meaningful only
  for the multi-round `answer_with_iteration` judge path). `run_id` passed to the
  single-pass path is accepted and ignored.

### Hard invariants (frozen)

1. **Re-auth never widens access.** On resume, any evidence that fails the current
   authorization check is dropped; the resumed run never leaks data the principal
   can no longer read (build plan §3623 "ACL 收紧不因旧 Cache/Checkpoint 泄露").
2. **Re-auth basis must be current.** Corpus discoverability + active document +
   active version + current ACL + unchanged `policy_version`. Any staleness → fail
   closed (abort the resumed run / drop the evidence).
3. **Cross-principal resume is refused.** A `run_id` checkpoint may only be resumed
   by the identical `tenant_id` / `user_id` / `session_id`; a mismatch aborts.
4. **Determinism.** Given identical re-auth outcomes, a run resumed at any round
   boundary produces the same `AnswerEnvelope` as an uninterrupted run.
5. **Metadata DB is the checkpoint source of truth.** The checkpoint table is
   applied idempotently by `apply_migrations`; checksums/round counters are the only
   recovery signal — never Qdrant / Parent Store / filesystem state.

---

## 2. Acceptance commands

```bash
# Full suite must stay green (baseline: 766 passed / 1 skipped) + new E-023 tests.
uv run pytest tests -q

# Quality gates (from build plan §23.7).
uv run ruff check .
uv run ruff format --check .
uv run mypy src/agentic_rag_enterprise
```

## 3. Files

- `migrations/013_e023_run_checkpoints.sql` (new) — `run_checkpoints` table.
- `src/agentic_rag_enterprise/storage/checkpoint_store.py` (new) — `RunCheckpoint`
  model + (de)serialization + `reauthorize_evidence` helper.
- `src/agentic_rag_enterprise/storage/metadata_store.py` — `save_run_checkpoint` /
  `load_run_checkpoint` / `mark_run_checkpoint_done` / `list_run_checkpoints`
  (mirroring the lease/reconciliation pattern).
- `src/agentic_rag_enterprise/services/chat_service.py` — resumable loop state +
  checkpoint save + `resume_run` + re-auth; accept `metadata_store` + `run_id`.
- `src/agentic_rag_enterprise/services/container.py` — wire `metadata_store` into
  `ChatService`.
- `src/agentic_rag_enterprise/api/schemas.py` — `run_id` + `resume` on `ChatRequest`.
- `src/agentic_rag_enterprise/api/routes/chat.py` — resume branch (thin, fail-closed).
- `tests/unit/test_checkpoint_store.py` (new), `tests/unit/test_chat_service_checkpoint.py`
  (new), `tests/unit/test_chat_api.py` (extend), `tests/integration/test_e023_checkpoint_resume.py` (new).
