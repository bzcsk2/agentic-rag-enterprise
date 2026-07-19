"""Integration tests for E-023 checkpoint + resume on the default app.

Unlike the unit tests (which hand-build a ``MetadataStore``), this suite drives
the REAL default-app container: documents are ingested through the genuine
ingestion pipeline into the shared Metadata DB + Qdrant, and the
:class:`ChatService` re-authorizes resumed evidence against the REAL active
documents. The retriever / model are hermetic fakes (permitted by the contract —
no LLM / network), but every persistence and re-authorization code path is the
production one.

Asserts the E-023 invariants end-to-end:

* the Metadata DB is the single source of truth for the checkpoint (invariant 5);
* a run resumed from a completed checkpoint equals the uninterrupted run
  (determinism, invariant 4);
* after an ACL tighten, resumed evidence the principal lost access to is DROPPED
  and never leaks, with an audit finding recorded (invariant 1 — "ACL 收紧不因旧
  Cache/Checkpoint 泄露");
* a mid-loop crash leaves a resumable ``running`` checkpoint that continues to
  the same answer.
"""

from __future__ import annotations

import re
from datetime import datetime

import pytest

from agentic_rag_enterprise.answer.envelope import Claim
from agentic_rag_enterprise.corpus.registry import InMemoryCorpusRegistry
from agentic_rag_enterprise.domain.corpus import CorpusConfig
from agentic_rag_enterprise.domain.evidence import Evidence as SnapshotEvidence
from agentic_rag_enterprise.domain.security import SecurityContext
from agentic_rag_enterprise.judge.deterministic_coverage_judge import (
    DeterministicCoverageJudge,
)
from agentic_rag_enterprise.judge.models import RequiredFact
from agentic_rag_enterprise.judge.query_fact_extractor import make_required_fact
from agentic_rag_enterprise.retrieval.fast_path import FastPathBackendError
from agentic_rag_enterprise.retrieval.models import CorpusNotDiscoverableError
from agentic_rag_enterprise.security.policy import ResourceAcl
from agentic_rag_enterprise.services.chat_service import ChatService
from agentic_rag_enterprise.services.claims_schema import ClaimExtraction
from agentic_rag_enterprise.services.container import (
    DefaultServiceContainer,
    get_default_container,
    reset_default_container,
)
from agentic_rag_enterprise.storage.vector_store import DenseEncoder, SparseEncoder
from tests.fixtures import FakeDenseEncoder, FakeSparseEncoder


@pytest.fixture(autouse=True)
def _fresh_container() -> None:
    reset_default_container()
    yield
    reset_default_container()


def _ctx() -> SecurityContext:
    return SecurityContext(
        request_id="r1",
        session_id="s1",
        tenant_id="t1",
        user_id="u1",
        policy_version="1.0",
    )


def _eng_corpus() -> CorpusConfig:
    return CorpusConfig(
        corpus_id="eng",
        tenant_id="t1",
        name="Eng",
        description="",
        domain="",
        owner="",
        source_type="wiki",
        capability_ids=[],
        enabled=True,
        searchable=True,
        security_policy_id="p",
        default_security_level="internal",
        created_at=datetime(2024, 1, 1),
        updated_at=datetime(2024, 1, 1),
    )


def _evidence(evidence_id: str, text: str, document_id: str) -> SnapshotEvidence:
    return SnapshotEvidence(
        evidence_id=evidence_id,
        tenant_id="t1",
        corpus_id="eng",
        document_id=document_id,
        document_version="v1",
        source_uri=f"inline://{document_id}",
        source_filename=f"{document_id}.md",
        text=text,
        text_hash=f"h-{evidence_id}",
        retrieval_query="q",
        authority_level=50,
        retrieved_at=datetime(2024, 1, 1),
        acl_policy_id="default",
        policy_version="1.0",
        retrieval_iteration=0,
    )


def _public_acl() -> ResourceAcl:
    return ResourceAcl(
        tenant_id="t1",
        security_level="public",
        acl_scope="tenant",
        allowed_user_ids=["u1"],
        allowed_group_ids=[],
        denied_user_ids=[],
        denied_group_ids=[],
    )


class _FakeRetriever:
    def __init__(self, evidence_map: dict[str, object], *, fault_query: str | None = None) -> None:
        self._map = evidence_map
        self._fault_query = fault_query
        self._faulted = False
        self.calls: list[tuple[str, int]] = []

    def retrieve_evidence(
        self,
        ctx: SecurityContext,
        query: str,
        corpus: CorpusConfig,
        top_k: object = None,
        *,
        dense_encoder: DenseEncoder,
        sparse_encoder: SparseEncoder,
        iteration: int = 0,
        plan_step_id: object = None,
    ) -> list[SnapshotEvidence]:
        self.calls.append((query, iteration))
        if corpus.tenant_id != ctx.tenant_id:
            raise CorpusNotDiscoverableError(
                f"corpus {corpus.corpus_id} not discoverable for {ctx.tenant_id}"
            )
        if self._fault_query is not None and query == self._fault_query and not self._faulted:
            self._faulted = True
            raise RuntimeError("simulated crash")
        payload = self._map.get(query, [])
        if isinstance(payload, Exception):
            raise payload
        return list(payload)


class _LoopModel:
    def invoke(self, messages, **kwargs):
        return ""

    def with_structured_output(self, schema, **kwargs):
        return self._Wrapper(self, schema)

    class _Wrapper:
        def __init__(self, model, schema):
            self._model = model
            self._schema = schema

        def invoke(self, messages, **kwargs):
            blob = "\n".join(m.get("content", "") for m in messages)
            claims = []
            for seg in re.split(r"(?=\[[A-Za-z0-9_-]+\])", blob):
                m = re.match(r"\[([A-Za-z0-9_-]+)\]\s*[^\n]*\n(.*?)(?:\n\n|\Z)", seg, re.DOTALL)
                if not m:
                    continue
                text = m.group(2).strip()
                if text:
                    claims.append(
                        Claim(claim_id=f"c{len(claims)}", text=text, evidence_ids=(m.group(1),))
                    )
            return ClaimExtraction(draft_answer="\n".join(c.text for c in claims), claims=claims)


def _ingest(container: DefaultServiceContainer, document_id: str, content: str) -> None:
    result = container.ingest(
        tenant_id="t1",
        corpus_id="eng",
        document_id=document_id,
        document_version="v1",
        content=content,
        acl=_public_acl(),
        job_id=f"job-{document_id}",
        security_level="public",
    )
    assert result.status.value in ("indexed", "already_indexed"), result


def _service(container: DefaultServiceContainer, retriever: _FakeRetriever) -> ChatService:
    # Real shared MetadataStore + real corpus registry from the container; only
    # retrieval / synthesis are faked (hermetic, contract-permitted).
    return ChatService(
        retriever=retriever,
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
        model=_LoopModel(),
        resolve_corpus=lambda cid: _eng_corpus(),
        metadata_store=container.metadata_store,
        judge=DeterministicCoverageJudge(),
        registry=container.corpus_registry,
    )


def _facts(*descs: str) -> list[RequiredFact]:
    return [make_required_fact(d) for d in descs]


def _vacation_map() -> dict[str, object]:
    return {
        "q": [_evidence("e1", "The vacation policy grants 20 days paid leave.", "d1")],
        "bonus structure": [_evidence("e2", "The bonus policy grants a 10% bonus.", "d2")],
    }


def _assert_same(a, b) -> None:
    assert a.completeness == b.completeness
    assert a.confidence == b.confidence
    assert a.stop_reason == b.stop_reason
    assert {e.evidence_id for e in a.evidence} == {e.evidence_id for e in b.evidence}
    assert a.answer_markdown == b.answer_markdown
    if a.coverage is not None and b.coverage is not None:
        assert a.coverage.overall_status == b.coverage.overall_status


def test_checkpoint_persists_on_shared_metadata_db_and_resume_matches() -> None:
    container = get_default_container()
    _ingest(container, "d1", "The vacation policy grants 20 days paid leave.")
    _ingest(container, "d2", "The bonus policy grants a 10% bonus.")

    svc = _service(container, _FakeRetriever(_vacation_map()))

    ref = svc.answer_with_iteration(
        "q", _ctx(), "eng", max_rounds=5, judge=DeterministicCoverageJudge(),
        required_facts=_facts("vacation policy", "bonus structure"),
    )

    svc.answer_with_iteration(
        "q", _ctx(), "eng", max_rounds=5, run_id="R1", judge=DeterministicCoverageJudge(),
        required_facts=_facts("vacation policy", "bonus structure"),
    )

    # The checkpoint lives on the REAL shared Metadata DB (invariant 5).
    row = container.metadata_store._conn.execute(
        "SELECT status FROM run_checkpoints WHERE run_id=?", ("R1",)
    ).fetchone()
    assert row is not None
    assert row["status"] == "completed"

    resumed = svc.resume_run("R1", _ctx())
    _assert_same(resumed, ref)


def test_resume_drops_revoked_evidence_after_acl_tighten_no_leak() -> None:
    container = get_default_container()
    _ingest(container, "d1", "The vacation policy grants 20 days paid leave.")
    _ingest(container, "d2", "The bonus policy grants a 10% bonus.")

    svc = _service(container, _FakeRetriever(_vacation_map()))
    svc.answer_with_iteration(
        "q", _ctx(), "eng", max_rounds=5, run_id="R2", judge=DeterministicCoverageJudge(),
        required_facts=_facts("vacation policy", "bonus structure"),
    )

    # Tighten d2's ACL so u1 can no longer read it (control-plane ACL tighten).
    mstore = container.metadata_store
    mstore.update_document_acl(
        "t1", "eng", "d2", "v1",
        security_level="public", acl_scope="restricted",
        allowed_user_ids=["other"], allowed_group_ids=[],
        denied_user_ids=[], denied_group_ids=[],
    )

    resumed = svc.resume_run("R2", _ctx())
    # The revoked evidence must never re-surface.
    assert {e.evidence_id for e in resumed.evidence} == {"e1"}
    assert all(e.document_id != "d2" for e in resumed.evidence)
    # The drop is auditable.
    findings = [
        dict(r)
        for r in mstore._conn.execute(
            "SELECT kind FROM reconciliation_findings"
        ).fetchall()
    ]
    assert any(f["kind"] == "resume_evidence_revoked" for f in findings)


def test_mid_loop_crash_leaves_resumable_checkpoint() -> None:
    container = get_default_container()
    _ingest(container, "d1", "The vacation policy grants 20 days paid leave.")
    _ingest(container, "d2", "The bonus policy grants a 10% bonus.")

    # First pass crashes on the gap query, leaving a `running` checkpoint.
    crash_retriever = _FakeRetriever(_vacation_map(), fault_query="bonus structure")
    svc = _service(container, crash_retriever)
    with pytest.raises(FastPathBackendError):
        svc.answer_with_iteration(
            "q", _ctx(), "eng", max_rounds=5, run_id="R3", judge=DeterministicCoverageJudge(),
            required_facts=_facts("vacation policy", "bonus structure"),
        )
    ck = container.metadata_store.load_run_checkpoint("R3")
    assert ck is not None
    assert ck.round_index == 1  # only round 0 had completed before the crash
    assert {e.evidence_id for e in ck.evidence} == {"e1"}

    # Resume continues and reaches the same sufficient answer.
    resumed = svc.resume_run("R3", _ctx())
    assert resumed.abstained is False
    assert resumed.completeness == "complete"
    assert {e.evidence_id for e in resumed.evidence} == {"e1", "e2"}

    ref = _service(container, _FakeRetriever(_vacation_map())).answer_with_iteration(
        "q", _ctx(), "eng", max_rounds=5, judge=DeterministicCoverageJudge(),
        required_facts=_facts("vacation policy", "bonus structure"),
    )
    _assert_same(resumed, ref)
