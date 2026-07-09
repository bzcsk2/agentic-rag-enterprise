from typing import Any

from pydantic import BaseModel, Field

from agentic_rag_enterprise.schemas import Evidence, GroundedAnswer, QueryPlan, SufficiencyDecision


class AgenticRagState(BaseModel):
    """State object passed through the Agentic RAG graph.

    The context window is not treated as the runtime state. This object is the
    materialized task state used for planning, retrieval, sufficiency checking,
    synthesis, trace, and replay.
    """

    user_query: str
    normalized_query: str | None = None
    plan: QueryPlan | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    sufficiency_decisions: list[SufficiencyDecision] = Field(default_factory=list)
    final_answer: GroundedAnswer | None = None

    iteration: int = 0
    tool_calls: int = 0
    visited_queries: set[str] = Field(default_factory=set)
    visited_documents: set[str] = Field(default_factory=set)
    stop_reason: str | None = None
    trace: list[dict[str, Any]] = Field(default_factory=list)

    def add_trace(self, event_type: str, payload: dict[str, Any]) -> None:
        self.trace.append({"event_type": event_type, "payload": payload})
