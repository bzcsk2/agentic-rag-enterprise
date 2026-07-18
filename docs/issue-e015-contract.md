# E-015 Issue Contract (M4) — Corpus / Capability Registry + three Corpus fixtures

First half of Milestone 4 (multi-Corpus retrieval, build plan §9 / §3597 / §5068).
Establishes the **control plane** for multi-Corpus: a permission-safe `CorpusRegistry`
and `CapabilityCatalog`, three reproducible Corpus fixtures, and the
`SecurityContext`-driven **discoverability** gate. This issue is strictly the
registry + fixtures; it does **not** add the data-plane router, cross-Corpus
retrieval, merge, or dedup — those are **E-016**.

The registry is the single source of truth for "which corpora exist and which a
caller may see". It reuses the existing `can_discover_corpus` / `allowed_corpus_ids`
discoverability gate (E-007 contract) and never returns a non-discoverable Corpus
to any caller. The existing single-Corpus `CorpusConfig` and Fast Path are extended,
not replaced: `resolve_corpus` continues to work, and the registry can act as its
backing source without changing retrieval behaviour.

## depends_on
- **E-007** — `can_discover_corpus(ctx, corpus_id)`, `allowed_corpus_ids` discoverability
  gate, `CorpusNotDiscoverableError`.
- **E-011 / E-012 / E-013 / E-014** — `CorpusConfig`, `Evidence`, `AnswerEnvelope`,
  `SecureRetriever`, `run_fast_path`, `ChatService` (single-Corpus path must keep
  passing).
- **Domain models** — `CorpusConfig` (`domain/corpus.py`), `SecurityContext`
  (`domain/security.py`).

## in_scope
- **`corpus/capability_registry.py`** — `Capability` literal set and a
  `CapabilityCatalog`:
  - Supported capabilities for the M4 multi-Corpus iteration are exactly
    `vector_search` and `document_reader` (build plan §9.1). `sql` / `api` / `graph`
    are declared in the catalog but **not** enabled for routing in M4 (interfaces
    are reserved, not executed).
  - `CapabilityCatalog.supports(capability: str) -> bool` — fail-closed: an unknown
    capability is never "supported".
- **`corpus/registry.py`** — `CorpusRegistry` (matches build plan §9.2 `Protocol`) +
  an `InMemoryCorpusRegistry` seeded from the three fixtures:
  - `get(corpus_id, security_context) -> CorpusConfig` — returns the config **only**
    if the caller may discover it; otherwise raises `CorpusNotDiscoverableError`
    (fail-closed). Never returns a Corpus whose `enabled` is `False` or `searchable`
    is `False` to a discoverer.
  - `list_searchable(security_context) -> list[CorpusConfig]` — returns **only**
    corpora the caller may discover (tenancy + `allowed_corpus_ids` + `enabled` +
    `searchable`). The returned list is the maximal set the router may ever see.
  - `resolve_candidates(query, security_context, limit) -> list[CorpusConfig]` —
    deterministic, capability-aware candidate resolution. Returns discoverable
    corpora whose `capability_ids` intersect the enabled M4 capabilities, ordered
    deterministically (stable, e.g. by `corpus_id`), truncated to `limit`. This is
    the **registry surface** for candidate discovery; the selection/confidence
    policy (top-1/top-2, `route_confidence`) is **E-016**, not here.
- **Three Corpus fixtures** — `product_docs`, `engineering_wiki`, `tickets` (build
  plan §9.4). Seeded in `corpus/fixtures.py` as reproducible `CorpusConfig` objects
  (same ids / tenant / domain / owner / capability_ids / authority_level as §9.4).
  All three share `tenant_id == "local"`; discoverability is driven by
  `SecurityContext.allowed_corpus_ids`, not by tenant separation (so the
  "discover only 2 of 3" scenario is exercised by `allowed_corpus_ids`).
- **`docs/issue-e015-contract.md`** (this file) + **`AGENTS.md`** update (M4 line
  corrected to match build plan §9 / Milestone 4 — no Planner DAG / Required-Fact
  Judge / iteration in M4).

## deferred_to
- **E-016** — permission-aware soft router (`CorpusCandidate` / `CorpusRoute`,
  §9.3), cross-Corpus retrieval via the existing `SecureRetriever`, Evidence merge
  and dedup, `corpora_used` accounting. E-015 only provides the discoverable
  candidate set the router consumes.
- **M5 / E-017 → E-018** — Typed Planner DAG, parallel / dependency multi-hop.
- **M6 / E-021** — Temporal scope, source authority, conflict reconciliation.
- Real SQL / API / graph execution (catalog reserves the names; M4 does not run them).

## allowed_paths (M4 / E-015 only)
- `src/agentic_rag_enterprise/corpus/` (NEW package): `capability_registry.py`,
  `registry.py`, `fixtures.py`.
- `src/agentic_rag_enterprise/domain/corpus.py` (reuse; no change required).
- `src/agentic_rag_enterprise/security/policy.py` (reuse `can_discover_corpus`).
- `tests/unit/corpus/`, `tests/security/` (new E-015 tests).
- `docs/issue-e015-contract.md`, `AGENTS.md`.
- **Reuse, no change:** `domain/security.py`, `retrieval/`, `services/chat_service.py`
  (single-Corpus path), `answer/`, `storage/`, `config.py`.

## forbidden
- No data-plane routing, no cross-Corpus retrieval, no merge/dedup (E-016).
- No Planner / DAG (M5).
- No change to the single-Corpus Fast Path behaviour or `resolve_corpus` contract.
- The registry must never hand a non-discoverable Corpus to a caller: `get` and
  `list_searchable` are fail-closed. A Corpus absent from / denied by
  `allowed_corpus_ids` must not appear in `list_searchable`, `get`, or
  `resolve_candidates` output.
- No model/LLM chooses the corpus set; the registry is the only source of
  discoverable corpora (build plan §9.2: "不得把全部 Corpus Map 交给模型后再依赖
  模型忽略无权限 Corpus").
- No upstream modifications; no reserved/placeholder runtime branches not exercised
  by the E-015 tests.

## acceptance_tests
- `tests/unit/corpus/test_registry.py` — `list_searchable` returns only
  `allowed_corpus_ids` ∩ enabled ∩ searchable; a caller allowed 2 of 3 sees exactly
  those 2 and never the third; `get` raises `CorpusNotDiscoverableError` for the
  third; disabled / non-searchable corpora are excluded; `resolve_candidates`
  returns only capability-matching discoverable corpora, deterministically ordered.
- `tests/unit/corpus/test_fixtures.py` — the three fixtures exist, carry the
  §9.4 ids / domain / owner / `capability_ids` / `authority_level`, and all three
  are discoverable to an unrestricted `local` context.
- `tests/unit/corpus/test_capability_catalog.py` — `vector_search` / `document_reader`
  supported; `sql` / `api` / `graph` reserved-but-not-enabled; unknown capability
  unsupported.
- `tests/security/test_corpus_discoverability.py` — `can_discover_corpus` +
  registry `get`/`list_searchable` agree; a non-discoverable corpus name/description
  never leaks into any returned config.
- **Regression:** `tests/unit/test_chat_service_iteration.py`,
  `tests/evals/test_evals_harness.py`, `tests/baseline/` and all E-011→E-020 tests
  remain green (single-Corpus Fast Path unaffected).
