# Issue E-021 — Temporal scope, source authority & conflict handling

**Milestone:** M6 — Temporal scope, source authority & conflict (`E-021`)
**Status:** contract frozen / implementation pending — **amended at this commit to fix three
main-path-breaking defects** (see §2a `as_of`-vs-`range` precedence, §4 `ConflictReport`
no longer carries `OverallStatus`, §4/§5 conflict detection now requires a structured
`assertion` parser). Acceptance of this (amended) doc unlocks
`domain/temporal.py`, `evidence/temporal.py`, `evidence/conflict_resolver.py`,
`evidence/models.py`, the `AnswerEnvelope.conflict_report` extension, and the test paths.
**Baseline:** `6356dc7` (main HEAD; includes M5 / E-018 CLOSED / ACCEPTED at `4d072bd`).
**Build plan refs:** §15 (conflict / temporality / authority), §7.6 (`Evidence` model),
§7.7 / §7.8 (`RequiredFact` / `FactCoverage` / `SufficiencyResult`), §7.9 (`AnswerEnvelope`),
§17.1 (future graph-state `temporal_scope` — *not* touched in this issue).
**Depends on:** E-011 (Evidence snapshot store), E-012 (Fast Path), E-013
(`AnswerEnvelope` / citation), E-019 / E-020 (`SufficiencyResult` coverage + iteration).
Reuses `domain/evidence.Evidence` fields — **no new `Evidence` field is introduced**.

---

## 1. Scope and non-goals

### In scope (evidence-stage, post-retrieval)

- `TemporalScope` model + deterministic `TemporalScopeParser` (no LLM / no NLP library).
- Temporal filter over an already-authorized `Evidence` collection.
- `ConflictResolver` with the five conflict categories and the four explicit
  auto-resolution rules from build plan §15.3.
- Unresolvable conflict → `overall_status = contradicted` with explicit source + time listing.
- The minimal `AnswerEnvelope` extension that carries the `ConflictReport`.
- MVP acceptance + knowledge-pollution tests.

### Non-goals (deferred / forbidden)

- **No change to `QueryPlan`, `PlanStep`, or the Executor protocol** (M5 frozen). The
  resolver runs in the evidence pipeline *after* retrieval, never inside the Planner / DAG.
- **No LLM time-reasoning chain, no value-extraction model, no NER.** Conflict detection is
  deterministic and conservative: candidate conflicts are created **only** under strict
  conditions (same-`document_id` version divergence, or a structured `assertion` parser
  extracting a *different* value on the *same* key with overlapping effective time). Differing
  full `text` alone **never** constitutes a conflict. Richer conflict extraction is a
  later-milestone capability.
- **No new `Evidence` field.** Everything the resolver needs already exists:
  `authority_level`, `effective_from`, `effective_to`, `deprecated`, `document_version`,
  `retrieved_at`, `rerank_score`, `retrieval_score`, `source_uri`, `source_filename`,
  `section_path`. Authority ranking also reads `CorpusConfig.authority_level` (already
  carried onto each `Evidence.authority_level` by the retriever).
- **No Planner / graph-state change.** `AgenticRagState.temporal_scope` (§17.1) is a *future*
  integration; this issue integrates via the `ChatService` call sites only.
- **No dependency on upstream** (`/vol4/Agent/agentic-rag-for-dummies`).

### Hard invariants (frozen)

1. The resolver only ever sees `Evidence` already returned by the **authorized** retrieval
   path (corpus-discoverability gate + parent second-auth + active-version gate). It must
   **never** reintroduce or consider any evidence that was not in that collection.
   → Unauthorized evidence never participates in conflict judgment.
2. Conflict results **preserve the `evidence_id` and source** (corpus / document / version /
   section / effective window) of every involved snapshot.
3. Resolution **never** selects a "most likely" answer by `retrieval_score` /
   `rerank_score`. Only the four explicit rules (version / time / authority / historical)
   may resolve a conflict; vector relevance is *not* a tie-breaker for truth.
4. When a conflict cannot be auto-resolved, the resolver emits `CONTRADICTED`; the pipeline
   then forces `SufficiencyResult.overall_status = "contradicted"` and lists the conflicting
   sources + applicable times. It does **not** emit a single deterministic conclusion from
   the resolver.

---

## 2. `TemporalScope` model

Lives in `domain/temporal.py` (stable shared domain model; the future graph-state import
target). Shape is taken verbatim from build plan §15.4 / §17.1:

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class TemporalScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: Literal["current", "as_of", "range", "unspecified"]
    as_of: datetime | None = None      # set when mode == "as_of"
    start: datetime | None = None      # set when mode == "range"
    end: datetime | None = None        # set when mode == "range"
```

Retrieval, the temporal filter, and the conflict resolver MUST all consume the **same**
`TemporalScope` instance for a given query (build plan §15.4: "检索和 SCA 必须使用同一
TemporalScope").

### 2a. Deterministic parser

`domain/temporal.py` (or a thin `parse_temporal_scope` in `evidence/temporal.py` delegating
to the domain model) — **`parse_temporal_scope(query: str, *, now: datetime | None = None)
-> TemporalScope`**.

Pure, deterministic keyword + regex table. No external NLP / date library, no LLM. The
following representative inputs define the MVP mapping (build plan §15.4):

| Query form | `mode` |
| --- | --- |
| "当前 API 版本是多少？" / "current" / "now" | `current` |
| "截至 2025-12-31 …" / "as of 2025-12-31" / "as_of 2025-12-31" / "截止 2025-12-31" | `as_of` (`as_of=2025-12-31`) |
| "2024 年发生了什么" / "between 2024-01-01 and 2024-12-31" / "2024-01-01 ~ 2024-12-31" | `range` (start/end inferred) |
| (no temporal marker) | `unspecified` |

Frozen mode-selection priority (first match wins — fixes the `as_of`-vs-`range` clash where
"截至 2025-12-31" could otherwise grab the bare `2025` as a year `range`):

1. **explicit range** — explicit range markers (`between … and …`, `from … to …`, `… 至 …`,
   `… 到 …`, `… 之间`, `… ~ …`). An explicit `start … end` pair uses the parsed bounds.
2. **as_of** — `截至` / `as of` / `as_of` / `截止` / `… 为止` followed by a parseable date
   → `as_of` with that date. **Guard (frozen):** when any `as_of` marker
   (`截至` / `as of` / `as_of` / `截止` / `… 为止`) is present, the bare-year rule below MUST
   NOT run — the query is `as_of`, never a year `range`. (This is what keeps
   "截至 2025-12-31" → `as_of`, not a `2025` range.)
3. **current** — `当前` / `现在` / `目前` / `current` / `now` / `today`.
4. **bare-year range** — a bare 4-digit year token or a `*年*` Chinese year reference
   *without* any of the markers above (e.g. "2024 年发生了什么"). A bare year `YYYY` is
   expanded to `start=YYYY-01-01`, `end=YYYY-12-31`; a bare `YYYY-MM-DD` to that day's
   `[00:00, 23:59:59]`.
5. **unspecified** — no temporal marker at all (fallback; treated like `current` for the
   filter but recorded distinctly so downstream can tell "user said nothing about time").

Date formats (whitelist, frozen): `YYYY-MM-DD`, `YYYY-MM-DD HH:MM`, `YYYY/MM/DD`,
`YYYY年MM月DD日`, `YYYY年MM月`, `YYYY年`, and the bare `YYYY`. Parsing is strict (unknown
formats → leave the field `None`, never guess). `now` is injectable (defaults to
`datetime.now()`) so tests are deterministic.

---

## 3. Temporal filter

`evidence/temporal.py`: `filter_by_temporal_scope(evidence, scope, *, now) ->
TemporalFilterResult`.

```python
class FilteredEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)
    evidence: SnapshotEvidence
    reason: Literal["deprecated", "expired", "not_yet_effective", "out_of_window"]


class TemporalFilterResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    scope: TemporalScope
    retained: tuple[SnapshotEvidence, ...]
    filtered_out: tuple[FilteredEvidence, ...]
```

Rules (all comparisons use the `SnapshotEvidence` `effective_from` / `effective_to` /
`deprecated` fields; `now` injected for `current`):

- **`current` / `unspecified`** (target = `now`):
  - drop `deprecated is True`;
  - drop `effective_to` is set **and** `effective_to < now` (expired);
  - drop `effective_from` is set **and** `effective_from > now` (not yet effective);
  - keep everything else (an evidence with `effective_from`/`effective_to` both `None` and
    not deprecated is always kept).
- **`as_of`** (target = `scope.as_of`): keep iff
  `effective_from is None or effective_from <= as_of` **and**
  `effective_to is None or effective_to >= as_of`. The `deprecated` flag is **ignored** for
  `as_of` (it reflects *current* state; we want the version that was in force at that date).
- **`range`** (window = `[start, end]`): keep iff the evidence effective window *overlaps*
  the scope window:
  `effective_from is None or effective_from <= end` **and**
  `effective_to is None or effective_to >= start`. The `deprecated` flag is **ignored**
  (same rationale as `as_of`).

The filter is **purity-preserving**: it never re-orders, never mutates snapshots, and never
adds evidence. Deterministic ordering of `retained` follows the input order.

---

## 4. Conflict model

`evidence/models.py`:

```python
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ConflictType(str, Enum):
    VALUE_CONFLICT = "value_conflict"      # same topic+key, different asserted value
    VERSION_CONFLICT = "version_conflict"  # same document_id, different document_version
    TIME_CONFLICT = "time_conflict"        # same topic, different effective windows
    SCOPE_CONFLICT = "scope_conflict"      # different key/subject, complementary not contradictory
    POLICY_CONFLICT = "policy_conflict"    # contradicts a formal policy / authoritative doc


class ConflictStatus(str, Enum):
    """Resolver-only verdict — the resolver cannot judge sufficiency (issue #2)."""
    NONE = "none"                 # no candidate conflict at all
    RESOLVED = "resolved"         # every candidate auto-resolved (version/time/authority/scope)
    CONTRADICTED = "contradicted"  # >=1 candidate could not be resolved


class ConflictResolution(str, Enum):
    AUTO_VERSION = "auto_resolved_version"        # rule 1
    AUTO_TIME = "auto_resolved_time"              # rule 2
    AUTO_AUTHORITY = "auto_resolved_authority"    # rule 3
    AUTO_SCOPE = "auto_resolved_scope"            # rule (scope: keep both, distinct)
    UNRESOLVED = "unresolved"                     # → CONTRADICTED


class AssertionExtraction(BaseModel):
    """Deterministic structured value extracted from one Evidence (issue #3)."""
    model_config = ConfigDict(frozen=True)
    is_structured: bool
    value: str | None = None                                  # normalized, e.g. "v2", "true", "60s"
    value_kind: Literal["version", "boolean", "quantity", "key_value"] | None = None
    key: str | None = None                                    # for key_value: the LHS key


class SourceRef(BaseModel):
    """Immutable pointer back to the conflicting Evidence (build plan §16.6)."""

    model_config = ConfigDict(frozen=True)
    evidence_id: str
    corpus_id: str
    document_id: str
    document_version: str
    section_path: tuple[str, ...] = ()
    source_filename: str = ""
    authority_level: int
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    is_temporary: bool = False   # effective_to is set → bounded / temporary, not permanent


class ConflictFinding(BaseModel):
    model_config = ConfigDict(frozen=True)
    conflict_id: str
    conflict_type: ConflictType
    topic_key: str                       # deterministic grouping key (e.g. normalized query)
    sources: tuple[SourceRef, ...]       # every involved snapshot, with provenance
    resolvable: bool
    resolution: ConflictResolution
    chosen_evidence_ids: tuple[str, ...] = ()  # empty when UNRESOLVED
    explanation: str = ""


class ConflictReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    scope: TemporalScope
    conflict_status: ConflictStatus      # resolver-only: none / resolved / contradicted
    findings: tuple[ConflictFinding, ...]
    resolved_evidence_ids: tuple[str, ...]   # evidence to feed downstream synthesis
    contradicted_fact_ids: tuple[str, ...] = ()
```

`topic_key` is **deterministic**: for the MVP it is the normalized query (whitespace-
collapsed, lower-cased, punctuation-stripped) supplied by the caller. `extract_assertion(text)
-> AssertionExtraction` is a **deterministic regex-only** parser (no LLM, no NER) supporting
only explicit forms:

* **version** — `(?:v|version|版本)\s*[:=]?\s*(\d+(?:\.\d+)*)`;
* **boolean** — `enabled|disabled|true|false|开启|关闭|启用|停用|是|否`;
* **quantity** — `(\d+(?:\.\d+)?)\s*(s|ms|seconds|minutes|分钟|秒|小时|mb|gb|kb|%|个|条)`;
* **key_value** — `([A-Za-z_一-龥]+)\s*[:：]\s*(\S+)`.

If none match → `is_structured=False`. **A candidate conflict is created only when:**
(1) same `document_id` with different `document_version` (`VERSION_CONFLICT`), **or**
(2) same `topic_key`, effective windows overlap, structured assertions extracted from ≥2
evidence, **and** the values differ — same `key` (or keyless) → `VALUE_CONFLICT`; different
`key`s (clearly distinct subjects, e.g. `timeout: 30s` vs `retries: 5`) → `SCOPE_CONFLICT`.
**Differing full `text` alone NEVER creates a candidate** — when no structured assertion can
be extracted (any involved evidence has `is_structured=False`), the pair is **pass-through**,
not a conflict. This is what prevents normal multi-evidence answers (an API-version note plus
a migration-step note) from being mis-flagged.

---

## 5. `ConflictResolver` rules

`evidence/conflict_resolver.py`: `ConflictResolver.resolve(evidence, scope, *, topic_key,
now=None) -> ConflictReport`.

For each `topic_key` group, examine the surviving (post-temporal-filter) evidence. **Candidate
conflicts are created ONLY under the strict deterministic conditions from §4 (issue #3):**

* **VERSION_CONFLICT** — same `document_id`, **different** `document_version` (always a
  candidate, regardless of extracted text).
* **VALUE_CONFLICT** — same `topic_key`, effective windows overlap, structured assertions
  extracted from ≥2 evidence, **same** key (or keyless) but **different** value.
* **SCOPE_CONFLICT** — same `topic_key`, structured assertions extracted from ≥2 evidence, but
  on **different** keys (clearly distinct subjects, e.g. `timeout: 30s` vs `retries: 5`) →
  complementary, **not** escalated.
* **Never** from differing full `text` alone: if any involved evidence has
  `is_structured=False`, the pair is **pass-through** (no candidate).

Then apply the **four explicit auto-resolution rules** from build plan §15.3 in this precedence:

1. **Same source, new version supersedes old (VERSION_CONFLICT, auto).**
   If conflicting evidence share the *same* `document_id` but differ in `document_version`
   → keep the newer version, drop the older. Version order is decided by `effective_from`
   (later wins); if `effective_from` is absent on both, fall back to lexicographic
   `document_version` (documented as imperfect, MVP-only). The older is tagged
   `VERSION_CONFLICT` / `AUTO_VERSION`, **not** escalated to `contradicted`.

2. **Explicit `effective_from` / `effective_to` settles the target time (TIME_CONFLICT).**
   If the conflict is between evidence with *different* effective windows (one bounded /
   temporary, one open-ended, or two non-overlapping windows), classify as `TIME_CONFLICT`:
   - For `current` / `unspecified`: the evidence *currently* effective (latest
     `effective_from`, or open-ended) wins → `AUTO_TIME`, not escalated — **unless** both
     are effective now and still assert different values (see rule 4).
   - For `as_of` / `range`: the temporal filter has already restricted to the window, so only
     at-window evidence reach here; if two at-window values still differ, proceed to rules 3/4.
   - **Temporary-rollback guard (frozen):** evidence with a set `effective_to` (`is_temporary
     = True`) is *never* auto-resolved as a permanent `VERSION_CONFLICT`. A Ticket describing
     a short-term rollback to v1 while an ADR states v2 is permanently current is a
     `TIME_CONFLICT`, **not** a permanent version supersede. If both the temporary and the
     permanent evidence are effective *now* and assert different values, this does **not**
     resolve by version/authority — it escalates per rule 4 (the model must surface both,
     not silently pick v2).

3. **Higher authority clearly overrides lower authority (VALUE_CONFLICT, auto).**
   If conflicting evidence are from *different* `document_id` (different sources) and their
   authority levels differ by a **clear** margin → keep the higher `authority_level`.
   "Clear" is frozen as `high.authority_level - low.authority_level >= AUTHORITY_OVERRIDE_MARGIN`
   (default `20`, configurable), which is exactly the Product-Doc(80) vs Ticket(40) case. The
   lower is tagged `VALUE_CONFLICT` / `AUTO_AUTHORITY`. This is also the mechanism for
   `POLICY_CONFLICT` (a formal policy / product doc vs an informal contradicting source).
   When the margin is below the threshold, authority does **not** decide → rule 4.

4. **Unresolvable → `CONTRADICTED` (no winner).**
   If none of rules 1–3 applies (e.g. two different authoritative docs, equal authority,
   conflicting values at the same time; or the temporary-rollback case from rule 2 where both
   are effective now) → emit a `finding` with `resolvable=False`, `resolution=UNRESOLVED`,
   list **all** involved `SourceRef`s **and their applicable times**, set
   `ConflictReport.conflict_status = CONTRADICTED`, and leave `chosen_evidence_ids` empty.
   The system must **not** choose a "most likely" answer.

`SCOPE_CONFLICT` (from the detection step): when structured assertions differ on **different**
keys (clearly distinct subjects), classify as `SCOPE_CONFLICT` with `resolution=AUTO_SCOPE`:
both are retained in `resolved_evidence_ids`, the finding notes the distinct scopes, and it is
**not** escalated — `conflict_status` stays `RESOLVED`/`NONE`. (Conservative principle still
holds: when in doubt about whether two values truly contradict, escalate to `CONTRADICTED`
rather than silently merge.)

The resolver returns `resolved_evidence_ids` = the surviving (kept) evidence across all
groups, in deterministic input order; downstream synthesis receives exactly this set.

> Note: `AUTHORITY_OVERRIDE_MARGIN` is a frozen default but configurable constant (kept in
> `evidence/conflict_resolver.py`, surfaced via `config.py` later if needed). The point of
> the margin is to forbid "marginal authority wins" — a 5-point gap must **not** auto-override.

---

## 6. Integration boundary (no Planner change)

The resolver sits **after** retrieval, **before** sufficiency / envelope. Frozen call sites
in `services/chat_service.py`:

```text
Retriever / Executor
  → Evidence collection (authorized, active-version gated)        [unchanged E-011/E-016]
  → Temporal filter    evidence/temporal.py: filter_by_temporal_scope   [NEW]
  → ConflictResolver   evidence/conflict_resolver.py: ConflictResolver.resolve  [NEW]
  → SufficiencyResult  (judge coverage; resolver CONTRADICTED forces overall_status="contradicted") [wired]
  → AnswerEnvelope     (carries ConflictReport; completeness="conflicted")   [extended]
```

- **Single-corpus `answer` / `_run_single_pass`** and **`answer_with_iteration`**: run the
  temporal filter + resolver on the accumulated `Evidence` *once*, after retrieval completes
  and before `_synthesize`. On a `contradicted` report, the synthesis step must present the
  conflict (both sources + times) rather than a single conclusion.
- **`answer_multi_corpus`**: run the filter + resolver on the **merged** evidence, after
  merge/dedup and before `_synthesize_multi_corpus`.
- The `TemporalScope` is derived once via `parse_temporal_scope(query)` at the top of each
  entry point and threaded through filter + resolver (single shared instance — §2).
- **ChatService conflict rule (frozen, issue #2):** the resolver runs *before* the Sufficiency
  Judge and only emits `conflict_status` (`NONE` / `RESOLVED` / `CONTRADICTED`) — it never
  judges `sufficient` / `partially_sufficient` / `insufficient`. After the judge produces its
  `SufficiencyResult`, the pipeline applies:
  * `conflict_status == CONTRADICTED` → force the final `SufficiencyResult.overall_status =
    "contradicted"` (and attach the report + `contradicted_fact_ids`). The resolver never
    invents any other sufficiency verdict.
  * `conflict_status in (NONE, RESOLVED)` → the judge's `overall_status` is left **unchanged**.
  This is exactly what guarantees normal no-conflict questions keep their existing M2–M5
  behavior.
- The `AnswerEnvelope` gains **one optional field** (backward-compatible, E-013 lock extended):

  ```python
  conflict_report: ConflictReport | None = None
  ```

  `_lock_state` extension: if `conflict_report is not None and
  conflict_report.conflict_status == CONTRADICTED` then `completeness` MUST be
  `"conflicted"` (and the answer must enumerate the sources/times from the report). This is
  the *only* envelope change and it does not alter the existing `abstained` / `insufficient`
  lock.
- Synthesis prompt (`_SYSTEM_PROMPT` / `_build_messages`): when a `CONTRADICTED` report is
  present, the model is instructed to **present both conflicting sources with their
  applicable times and cite both `evidence_id`s — never pick a single answer**. This is the
  only prompt change; it remains model-free (no new LLM call type).

Nothing in `planner/` (`QueryPlan`, `PlanStep`, `executor.py`, `result.py`, `budget.py`,
`tool_registry.py`) is modified.

---

## 7. MVP acceptance matrix

The five build-plan §26 scenario 8 / 9 (M6 exit gate) cases plus the two knowledge-
pollution cases (build plan risk "旧知识覆盖新知识" + the spec's explicit pollution
requirement) and the four cross-cutting invariants:

1. **Current question, new version covers old** — same `document_id`, v2 vs v1; resolver
   applies rule 1 (`AUTO_VERSION`), returns v2 only, `conflict_status == RESOLVED`
   (not `CONTRADICTED`).
2. **`as_of` historical** — "截至 2025-12-31 …"; temporal filter (rule §3 `as_of`) retains
   only the version effective at that date; the later version is not mis-used.
3. **Authority conflict** — Product Doc (authority 80) vs Ticket (authority 40) assert
   different values; resolver applies rule 3 (`AUTO_AUTHORITY`, margin 40 ≥ 20), keeps the
   Product Doc, Ticket not escalated.
4. **Temporary rollback** — Ticket with `effective_from`/`effective_to` (bounded, a short v1
   rollback) contradicts an open-ended ADR (v2 current); resolver classifies `TIME_CONFLICT`
   and does **not** treat it as a permanent `VERSION_CONFLICT`; if both are effective *now*
   with different values, it escalates to `contradicted` (both listed) rather than silently
   choosing v2.
5. **Unresolvable conflict** — two equal-authority, currently-effective, differing-value
   sources (structured assertions on the same key disagree, no authority margin); resolver
   `conflict_status = CONTRADICTED` → pipeline `SufficiencyResult.overall_status =
   contradicted`, no unique conclusion emitted, both `SourceRef`s (with times) preserved.
6. **Knowledge pollution — low-authority vs high-authority** — Ticket(40) vs Product Doc(80)
   conflict resolves to the Product Doc (authority rule), never the reverse.
7. **Knowledge pollution — new vs old document** — newer `document_version` of the same
   source supersedes the old (version rule), old not presented as current.
8. **Unauthorized evidence excluded** — evidence the retrieval path did not authorize (e.g.
   from a corpus the principal cannot read) is never passed to the resolver, so it cannot
   affect conflict outcomes.
9. **Conflict result keeps Evidence ID + source** — every `ConflictFinding.sources` carries
   `evidence_id`, `document_id`, `document_version`, `section_path`, `effective_from/to`.
10. **No vector-relevance selection** — resolution never uses `retrieval_score` /
    `rerank_score` to pick a winning fact; only version / time / authority / scope rules.
11. **M2–M5 regression** — full `pytest` (baseline / unit / security / integration / evals)
    stays green; single-corpus Fast Path `answer`, multi-corpus `answer_multi_corpus`, and
    the E-019/E-020 iteration loop behave identically when no temporal/conflict signal exists
    (`unspecified` scope + no structured-assertion divergence → resolver returns
    `conflict_status = NONE`, Sufficiency Judge output unchanged).
12. **Planner unchanged** — `QueryPlan` / `PlanStep` / `executor.py` remain as in E-017/E-018;
    the resolver is reachable without any Planner-core modification (M6 exit gate:
    "不需要修改 Planner 核心协议即可接入").

## 8. Quality gates (implementation)

- `ruff check src tests`, `ruff format --check .`, `uv run mypy src/agentic_rag_enterprise`
  clean.
- New `tests/unit/evidence/test_temporal.py` (parser + filter),
  `tests/unit/evidence/test_conflict_resolver.py` (rules 1–4 + the 5 acceptance scenarios +
  the 2 pollution cases + invariants 8–10), and an integration test
  `tests/integration/test_e021_evidence_pipeline.py` wiring filter + resolver into
  `ChatService` (single-corpus + multi-corpus) asserting `completeness="conflicted"` on
  unresolvable conflicts.
- Full `pytest` (incl. `tests/baseline/`) green; M2–M5 regression unaffected.
- Architecture test: `ConflictResolver` has no import dependency on `planner/` and receives
  only already-authorized `Evidence`.

---

### Contract-only commit boundary

This freeze commits only `docs/issue-e021-contract.md` + `AGENTS.md`. Implementation
(`domain/temporal.py`, `evidence/temporal.py`, `evidence/conflict_resolver.py`,
`evidence/models.py`, the `AnswerEnvelope.conflict_report` extension, and the test paths)
opens **after** this contract is accepted. Do **not** enter M7 (checkpoint / backup /
health / index migration) until E-021 is closed.
