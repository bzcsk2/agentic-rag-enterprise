"""Unit tests for E-019 DeterministicCoverageJudge (build plan §14.1–§14.3)."""

from datetime import datetime

from agentic_rag_enterprise.domain.evidence import Evidence as SnapshotEvidence
from agentic_rag_enterprise.judge.deterministic_coverage_judge import (
    DeterministicCoverageJudge,
)
from agentic_rag_enterprise.judge.models import FactStatus, RequiredFact


def _ev(evidence_id: str, text: str, tenant_id: str = "t1") -> SnapshotEvidence:
    return SnapshotEvidence(
        evidence_id=evidence_id,
        tenant_id=tenant_id,
        corpus_id="eng",
        document_id="d1",
        document_version="v1",
        source_uri="inline://d1",
        source_filename="d1.md",
        text=text,
        text_hash="h",
        retrieval_query="q",
        authority_level=50,
        retrieved_at=datetime(2024, 1, 1),
        acl_policy_id="default",
        policy_version="1.0",
        retrieval_iteration=0,
    )


def _fact(desc: str) -> RequiredFact:
    return RequiredFact(fact_id=f"f_{desc}", description=desc)


def test_supported() -> None:
    judge = DeterministicCoverageJudge()
    res = judge.judge(
        query="q",
        required_facts=[_fact("vacation policy")],
        evidence=(_ev("e1", "The vacation policy grants 20 days paid leave per year."),),
    )
    assert res.overall_status == "sufficient"
    assert res.fact_coverage[0].status is FactStatus.SUPPORTED


def test_partially_supported() -> None:
    judge = DeterministicCoverageJudge()
    # 6 fact tokens, only 2 overlap the evidence (< 50%) -> partial.
    res = judge.judge(
        query="q",
        required_facts=[_fact("the quarterly revenue target for the emea region expansion")],
        evidence=(_ev("e1", "the quarterly revenue increased"),),
    )
    assert res.fact_coverage[0].status is FactStatus.PARTIALLY_SUPPORTED


def test_missing_when_no_overlap() -> None:
    judge = DeterministicCoverageJudge()
    res = judge.judge(
        query="q",
        required_facts=[_fact("secret project codename")],
        evidence=(_ev("e1", "the weather is sunny today"),),
    )
    assert res.fact_coverage[0].status is FactStatus.MISSING
    assert res.overall_status == "insufficient"


def test_not_retrievable_when_empty_evidence() -> None:
    judge = DeterministicCoverageJudge()
    res = judge.judge(
        query="q",
        required_facts=[_fact("secret project codename")],
        evidence=(),
    )
    assert res.fact_coverage[0].status is FactStatus.NOT_RETRIEVABLE


def test_contradicted_with_negation() -> None:
    judge = DeterministicCoverageJudge()
    res = judge.judge(
        query="q",
        required_facts=[_fact("office in new york")],
        evidence=(_ev("e1", "The office is not in new york; it is in boston."),),
    )
    assert res.fact_coverage[0].status is FactStatus.CONTRADICTED
    assert res.overall_status == "contradicted"


def test_overall_priority_contradicted_beats_supported() -> None:
    judge = DeterministicCoverageJudge()
    res = judge.judge(
        query="q",
        required_facts=[
            _fact("vacation policy"),
            _fact("office in new york"),
        ],
        evidence=(
            _ev("e1", "The vacation policy grants 20 days paid leave per year."),
            _ev("e2", "The office is not in new york; it is in boston."),
        ),
    )
    assert res.overall_status == "contradicted"


def test_next_queries_emitted_for_missing() -> None:
    judge = DeterministicCoverageJudge()
    res = judge.judge(
        query="q",
        required_facts=[_fact("secret project codename")],
        evidence=(_ev("e1", "the weather is sunny"),),
    )
    assert res.fact_coverage[0].next_queries == ("secret project codename",)
    assert res.next_queries == ("secret project codename",)


def test_non_latin_fact_is_ambiguous_not_supported() -> None:
    # A Required Fact with no ASCII/matchable tokens (e.g. Chinese) must fail
    # closed to AMBIGUOUS, never be falsely marked SUPPORTED (P1-4).
    judge = DeterministicCoverageJudge()
    res = judge.judge(
        query="q",
        required_facts=[_fact("员工休假政策")],
        evidence=(_ev("e1", "员工每年享有20天带薪年假。"),),
    )
    assert res.fact_coverage[0].status is FactStatus.AMBIGUOUS


def test_stopword_only_fact_is_ambiguous_not_supported() -> None:
    # A fact made entirely of stopwords has no matchable token -> AMBIGUOUS.
    judge = DeterministicCoverageJudge()
    res = judge.judge(
        query="q",
        required_facts=[_fact("the and for")],
        evidence=(_ev("e1", "the bonus structure includes equity grants"),),
    )
    assert res.fact_coverage[0].status is FactStatus.AMBIGUOUS


def test_one_third_overlap_is_partial_not_supported() -> None:
    # 3 fact tokens, only 1 overlaps the evidence -> partial (not supported).
    judge = DeterministicCoverageJudge()
    res = judge.judge(
        query="q",
        required_facts=[_fact("alpha beta gamma")],
        evidence=(_ev("e1", "alpha delta epsilon"),),
    )
    assert res.fact_coverage[0].status is FactStatus.PARTIALLY_SUPPORTED


def test_two_fifth_overlap_is_partial_not_supported() -> None:
    # 5 fact tokens, only 2 overlap the evidence -> partial (not supported).
    judge = DeterministicCoverageJudge()
    res = judge.judge(
        query="q",
        required_facts=[_fact("alpha beta gamma delta epsilon")],
        evidence=(_ev("e1", "alpha beta zeta eta theta"),),
    )
    assert res.fact_coverage[0].status is FactStatus.PARTIALLY_SUPPORTED
