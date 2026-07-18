"""Unit tests for E-020 StopPolicy (build plan §14.5)."""

from agentic_rag_enterprise.judge.stop_policy import StopPolicy


def test_stop_on_sufficient() -> None:
    d = StopPolicy().decide(
        round=0,
        max_rounds=3,
        overall_status="sufficient",
        can_continue=True,
        new_evidence_ids={"e1"},
        new_covered_fact_ids=set(),
    )
    assert d.should_stop and d.reason == "sufficient"


def test_stop_on_max_rounds() -> None:
    d = StopPolicy().decide(
        round=2,
        max_rounds=3,
        overall_status="insufficient",
        can_continue=True,
        new_evidence_ids={"e1"},
        new_covered_fact_ids=set(),
    )
    assert d.should_stop and d.reason == "max_rounds"


def test_stop_on_no_new_evidence_after_two_consecutive_no_gain_rounds() -> None:
    # Build plan §14.5/§14.6: no_new_evidence only after TWO consecutive no-gain
    # rounds. First no-gain round must CONTINUE so a synonym/alternative query can
    # still be tried (the old impl stopped after a single no-gain round).
    p = StopPolicy()
    d1 = p.decide(
        round=1,
        max_rounds=4,
        overall_status="partially_sufficient",
        can_continue=True,
        new_evidence_ids=set(),
        new_covered_fact_ids=set(),
    )
    assert not d1.should_stop and d1.reason == "continue"
    d2 = p.decide(
        round=2,
        max_rounds=4,
        overall_status="partially_sufficient",
        can_continue=True,
        new_evidence_ids=set(),
        new_covered_fact_ids=set(),
    )
    assert d2.should_stop and d2.reason == "no_new_evidence"


def test_new_content_counts_as_gain() -> None:
    # §14.6: a new document version / new text hash (new_content) is a gain even
    # when no new Evidence id appeared, so id-only novelty is never the sole signal.
    p = StopPolicy()
    d = p.decide(
        round=1,
        max_rounds=5,
        overall_status="partially_sufficient",
        can_continue=True,
        new_evidence_ids=set(),
        new_covered_fact_ids=set(),
        new_content=True,
    )
    assert not d.should_stop and d.reason == "continue"


def test_continue_when_new_evidence_present() -> None:
    d = StopPolicy().decide(
        round=1,
        max_rounds=3,
        overall_status="partially_sufficient",
        can_continue=True,
        new_evidence_ids={"e2"},
        new_covered_fact_ids=set(),
    )
    assert not d.should_stop and d.reason == "continue"


def test_stop_on_budget_exhausted() -> None:
    d = StopPolicy().decide(
        round=0,
        max_rounds=3,
        overall_status="insufficient",
        can_continue=True,
        new_evidence_ids={"e1"},
        new_covered_fact_ids=set(),
        budget_remaining=0.0,
    )
    assert d.reason == "budget_exhausted"


def test_stop_on_judge_failure() -> None:
    d = StopPolicy().decide(
        round=0,
        max_rounds=3,
        overall_status="insufficient",
        can_continue=True,
        new_evidence_ids={"e1"},
        new_covered_fact_ids=set(),
        judge_ok=False,
    )
    assert d.reason == "tool_unavailable"


def test_stop_on_all_sources_exhausted() -> None:
    d = StopPolicy().decide(
        round=0,
        max_rounds=3,
        overall_status="insufficient",
        can_continue=False,
        new_evidence_ids={"e1"},
        new_covered_fact_ids=set(),
    )
    assert d.reason == "all_sources_exhausted"


def test_continue_when_new_covered_fact() -> None:
    d = StopPolicy().decide(
        round=1,
        max_rounds=3,
        overall_status="partially_sufficient",
        can_continue=True,
        new_evidence_ids=set(),
        new_covered_fact_ids={"a"},
    )
    assert not d.should_stop and d.reason == "continue"
