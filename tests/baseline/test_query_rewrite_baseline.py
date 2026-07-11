"""Baseline characterization for query rewriting capability.

This capability is NOT YET IMPLEMENTED in the target. The current PlannerAgent
is the only query-processing scaffold, and it returns a single-hop plan without
LLM-based rewriting or clarification.

Once the corresponding capability Issue ports upstream's rewrite_query and
clarification nodes, this file must be expanded with actual rewrite behavior
tests.
"""

from agentic_rag_enterprise.agents.planner import PlannerAgent
from agentic_rag_enterprise.schemas import QueryPlan


def test_planner_returns_single_hop_plan() -> None:
    agent = PlannerAgent()
    plan = agent.plan("What is the capital of France?")
    assert isinstance(plan, QueryPlan)
    assert plan.task_type == "single_hop"
    assert plan.required_facts == ["What is the capital of France?"]


def test_planner_subquestion_matches_query() -> None:
    agent = PlannerAgent()
    plan = agent.plan("test query")
    assert len(plan.subquestions) == 1
    sq = plan.subquestions[0]
    assert sq.id == "q1"
    assert sq.question == "test query"
    assert sq.target_corpora == []
    assert sq.depends_on == []


# Future rewrite_query tests (after port from upstream):
# - test_rewrite_clear_query_returns_rewritten
# - test_rewrite_unclear_query_requests_clarification
# - test_rewrite_follow_up_integrates_context
