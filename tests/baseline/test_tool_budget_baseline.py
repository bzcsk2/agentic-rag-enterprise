"""Baseline characterization tests for tool call and iteration budget enforcement.

The current scaffold has config defaults and a runtime loop bounded by
max_iterations. Full enforcement of MAX_TOOL_CALLS against LangGraph tool
execution will be introduced when the upstream graph is ported in the
corresponding capability Issue.
"""

from agentic_rag_enterprise.config import settings
from agentic_rag_enterprise.graph.runtime import AgenticRagRuntime


def test_max_iterations_default() -> None:
    assert settings.max_iterations == 3


def test_max_tool_calls_default() -> None:
    assert settings.max_tool_calls == 12


def test_max_retrieval_top_k_default() -> None:
    assert settings.max_retrieval_top_k == 8


def test_runtime_stops_at_sufficient_context() -> None:
    runtime = AgenticRagRuntime()
    state = runtime.run("any query")
    assert state.iteration == 1
    assert state.stop_reason == "sufficient_context"


def test_runtime_tool_calls_increments() -> None:
    runtime = AgenticRagRuntime()
    state = runtime.run("any query")
    assert state.tool_calls == 1


# Future budget tests (after corresponding capability Issue):
# - test_runtime_hits_max_tool_calls
# - test_tool_node_enforces_limit
# - test_graph_recursion_limit
