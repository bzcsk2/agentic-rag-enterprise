"""Baseline characterization tests for graph routing and agent scaffold behavior.

Covers AgenticRagRuntime, AgenticRagState, PlannerAgent, SufficientContextAgent,
SynthesisAgent, and TraceRecorder. All agents use deterministic mock implementations;
no LLM, no network, no external storage.
"""

from agentic_rag_enterprise.agents.planner import PlannerAgent
from agentic_rag_enterprise.agents.sufficient_context import SufficientContextAgent
from agentic_rag_enterprise.agents.synthesis import SynthesisAgent
from agentic_rag_enterprise.graph.runtime import AgenticRagRuntime
from agentic_rag_enterprise.graph.state import AgenticRagState
from agentic_rag_enterprise.observability.trace import TraceRecorder
from agentic_rag_enterprise.schemas import (
    Evidence,
    GroundedAnswer,
    QueryPlan,
    SufficiencyDecision,
    SufficiencyStatus,
)


# --- AgenticRagState ---


def test_state_defaults() -> None:
    state = AgenticRagState(user_query="q")
    assert state.user_query == "q"
    assert state.normalized_query is None
    assert state.plan is None
    assert state.evidence == []
    assert state.sufficiency_decisions == []
    assert state.final_answer is None
    assert state.iteration == 0
    assert state.tool_calls == 0
    assert state.visited_queries == set()
    assert state.visited_documents == set()
    assert state.stop_reason is None
    assert state.trace == []


def test_state_with_normalized_query() -> None:
    state = AgenticRagState(user_query="  test  ", normalized_query="test")
    assert state.normalized_query == "test"


def test_state_add_trace() -> None:
    state = AgenticRagState(user_query="q")
    state.add_trace("plan", {"task": "single_hop"})
    assert len(state.trace) == 1
    assert state.trace[0]["event_type"] == "plan"
    assert state.trace[0]["payload"] == {"task": "single_hop"}


def test_state_multiple_traces_appended() -> None:
    state = AgenticRagState(user_query="q")
    state.add_trace("retrieve", {"count": 1})
    state.add_trace("synthesis", {"done": True})
    assert len(state.trace) == 2


# --- AgenticRagRuntime ---


def test_runtime_returns_grounded_answer_shape() -> None:
    runtime = AgenticRagRuntime()
    state = runtime.run("What is Agentic RAG?")
    assert state.plan is not None
    assert len(state.evidence) == 1
    assert len(state.sufficiency_decisions) == 1
    assert state.sufficiency_decisions[-1].status == SufficiencyStatus.SUFFICIENT
    assert state.final_answer is not None
    assert sorted(state.final_answer.citations) == ["mock-evidence-1"]
    assert state.iteration == 1
    assert state.tool_calls == 1
    assert state.stop_reason == "sufficient_context"


def test_runtime_trace_events_recorded() -> None:
    runtime = AgenticRagRuntime()
    state = runtime.run("test")
    assert len(state.trace) == 4
    assert [t["event_type"] for t in state.trace] == [
        "plan",
        "retrieve",
        "sufficiency",
        "synthesis",
    ]


def test_runtime_evidence_includes_mock_evidence() -> None:
    runtime = AgenticRagRuntime()
    state = runtime.run("test query")
    assert len(state.evidence) == 1
    ev = state.evidence[0]
    assert ev.evidence_id == "mock-evidence-1"


# --- PlannerAgent ---


def test_planner_returns_query_plan() -> None:
    agent = PlannerAgent()
    plan = agent.plan("What is RAG?")
    assert isinstance(plan, QueryPlan)
    assert plan.task_type == "single_hop"


# --- SufficientContextAgent ---


def test_sca_insufficient_without_evidence() -> None:
    agent = SufficientContextAgent()
    plan = PlannerAgent().plan("test")
    decision = agent.judge("test", plan, [])
    assert decision.status == SufficiencyStatus.INSUFFICIENT
    assert decision.next_queries == ["test"]
    assert "No evidence" in decision.reason


def test_sca_sufficient_with_evidence() -> None:
    agent = SufficientContextAgent()
    plan = PlannerAgent().plan("test")
    evidence = [
        Evidence(
            evidence_id="e1",
            corpus_id="c1",
            document_id="d1",
            chunk_id="ch1",
            text="evidence text",
        )
    ]
    decision = agent.judge("test", plan, evidence)
    assert decision.status == SufficiencyStatus.SUFFICIENT
    assert decision.covered_facts == plan.required_facts
    assert "Evidence is present" in decision.reason


# --- SynthesisAgent ---


def test_synthesis_abstains_on_insufficient() -> None:
    agent = SynthesisAgent()
    decision = SufficiencyDecision(
        status=SufficiencyStatus.INSUFFICIENT,
        reason="No evidence.",
    )
    answer = agent.synthesize("test", [], decision)
    assert isinstance(answer, GroundedAnswer)
    assert answer.abstained is True
    assert "reliably" in answer.answer


def test_synthesis_returns_citations_when_sufficient() -> None:
    agent = SynthesisAgent()
    evidence = [
        Evidence(
            evidence_id="e1",
            corpus_id="c1",
            document_id="d1",
            chunk_id="ch1",
            text="fact 1",
        )
    ]
    decision = SufficiencyDecision(
        status=SufficiencyStatus.SUFFICIENT,
        reason="Enough evidence.",
    )
    answer = agent.synthesize("test", evidence, decision)
    assert answer.abstained is False
    assert "e1" in answer.citations
    assert answer.confidence == "medium"


# --- TraceRecorder ---


def test_trace_recorder_empty() -> None:
    recorder = TraceRecorder()
    assert recorder.dump() == []


def test_trace_recorder_record_and_dump() -> None:
    recorder = TraceRecorder()
    recorder.record("plan", {"task": "single_hop"})
    recorder.record("retrieve", {"hits": 1})
    events = recorder.dump()
    assert len(events) == 2
    assert events[0]["event_type"] == "plan"
    assert events[1]["payload"] == {"hits": 1}
