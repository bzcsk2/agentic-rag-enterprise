"""Unit tests for the E-013 answer package (build plan §7.9 / §16).

Hermetic: fake ``Evidence`` snapshots and ``FastPathResult`` objects, no Qdrant
and no LLM. Asserts the envelope is built with resolvable immutable citations on
the sufficient path, an abstained refusal with no fabricated facts on the
insufficient path, dangling citations are rejected, and unsupported critical
claims are removed with ``completeness`` downgraded to ``partial``.
"""

from datetime import datetime

import pytest

from agentic_rag_enterprise.answer import (
    AnswerEnvelope,
    Claim,
    build_answer_envelope,
    conservative_refusal,
    format_citation_panel,
    render_citations,
    verify_claims,
)
from agentic_rag_enterprise.domain.evidence import Evidence as SnapshotEvidence
from agentic_rag_enterprise.domain.security import SecurityContext
from agentic_rag_enterprise.retrieval.fast_path import (
    FastPathResult,
    FastPathSufficiency,
    FastPathStopReason,
)


def _evidence(evidence_id: str = "e1", document_id: str = "d1") -> SnapshotEvidence:
    return SnapshotEvidence(
        evidence_id=evidence_id,
        tenant_id="t1",
        corpus_id="eng",
        document_id=document_id,
        document_version="v1",
        source_uri=f"inline://{document_id}",
        source_filename=f"{document_id}.md",
        text="some grounded body",
        text_hash="h",
        retrieval_query="q",
        authority_level=50,
        retrieved_at=datetime(2024, 1, 1),
        acl_policy_id="default",
        policy_version="1.0",
        retrieval_iteration=0,
    )


def _ctx() -> SecurityContext:
    return SecurityContext(
        request_id="r", session_id="s", tenant_id="t1", user_id="u1", policy_version="1.0"
    )


def _sufficient(evidence: SnapshotEvidence | None = None) -> FastPathResult:
    ev = evidence or _evidence()
    return FastPathResult(
        query="q",
        corpus_id="eng",
        tenant_id="t1",
        evidence=(ev,),
        sufficiency=FastPathSufficiency.SUFFICIENT,
        stop_reason=FastPathStopReason.EVIDENCE_FOUND,
    )


def _insufficient() -> FastPathResult:
    return FastPathResult(
        query="q",
        corpus_id="eng",
        tenant_id="t1",
        evidence=(),
        sufficiency=FastPathSufficiency.INSUFFICIENT,
        stop_reason=FastPathStopReason.NO_EVIDENCE,
    )


def test_sufficient_path_builds_envelope_with_resolvable_citations() -> None:
    ev = _evidence()
    claims = [Claim(claim_id="C1", text="fact", importance="critical", evidence_ids=["e1"])]
    env = build_answer_envelope(_sufficient(ev), _ctx(), answer_markdown="answer", claims=claims)

    assert env.abstained is False
    assert env.completeness == "complete"
    assert env.confidence == "high"
    assert env.iterations == 1
    assert env.tool_calls == 1
    assert env.corpora_used == ("eng",)
    assert env.stop_reason == "evidence_found"
    assert len(env.evidence) == 1
    assert len(env.claims) == 1

    # Every citation resolves to a snapshot and carries the immutable refs.
    citations = render_citations([ev])
    assert len(citations) == 1
    cit = citations[0]
    assert cit.index == 1
    assert cit.evidence_id == "e1"
    assert cit.document_version == "v1"
    assert cit.text_hash == "h"
    assert cit.policy_version == "1.0"
    assert cit.corpus_id == "eng"
    # UI panel renders the immutable source coordinates.
    panel = format_citation_panel(citations)
    assert "[1] eng / d1" in panel


def test_insufficient_path_produces_abstained_refusal() -> None:
    env = build_answer_envelope(_insufficient(), _ctx(), answer_markdown="ignored")

    assert env.abstained is True
    assert env.claims == ()
    assert env.evidence == ()
    assert env.citations == ()
    assert env.completeness == "insufficient"
    assert env.confidence == "low"
    assert env.stop_reason == "no_evidence"
    # No fabricated fact; no document name or content leaked (build plan §16.2).
    assert "d1" not in env.answer_markdown
    assert "doc" not in env.answer_markdown
    assert env.answer_markdown.startswith("I cannot answer this reliably")


def test_dangling_citation_rejected() -> None:
    # Constructing an envelope whose claim cites absent evidence must fail the
    # validator (no dangling citation allowed), independent of the builder.
    ev = _evidence()
    with pytest.raises(ValueError):
        AnswerEnvelope(
            request_id="r",
            session_id="s",
            answer_markdown="a",
            claims=(Claim(claim_id="C1", text="x", evidence_ids=["ghost"]),),
            evidence=(ev,),
            completeness="complete",
            confidence="high",
            stop_reason="evidence_found",
            abstained=False,
        )


def test_unsupported_critical_claim_removed_and_downgraded() -> None:
    ev = _evidence()
    verification = verify_claims(
        [Claim(claim_id="C1", text="x", importance="critical", evidence_ids=["ghost"])],
        {ev.evidence_id},
    )
    assert verification.any_critical_unsupported is True
    assert verification.kept_claims == []
    assert len(verification.removed_claims) == 1

    env = build_answer_envelope(
        _sufficient(ev),
        _ctx(),
        answer_markdown="answer",
        claims=[Claim(claim_id="C1", text="x", importance="critical", evidence_ids=["ghost"])],
    )
    # Unsupported critical claim removed and completeness downgraded.
    assert env.claims == ()
    assert env.completeness == "partial"
    assert env.confidence == "medium"


def test_abstained_envelope_state_locked() -> None:
    ev = _evidence()
    # abstained but carrying claims/evidence -> rejected.
    with pytest.raises(ValueError):
        AnswerEnvelope(
            request_id="r",
            session_id="s",
            answer_markdown="a",
            claims=(Claim(claim_id="C1", text="x"),),
            evidence=(ev,),
            completeness="insufficient",
            confidence="low",
            stop_reason="no_evidence",
            abstained=True,
        )
    # completeness 'insufficient' requires abstained=True.
    with pytest.raises(ValueError):
        AnswerEnvelope(
            request_id="r",
            session_id="s",
            answer_markdown="a",
            claims=(),
            evidence=(),
            completeness="insufficient",
            confidence="low",
            stop_reason="no_evidence",
            abstained=False,
        )
    # conservative_refusal always yields a valid locked envelope.
    env = conservative_refusal(_insufficient(), _ctx())
    assert env.abstained is True
    assert env.completeness == "insufficient"
