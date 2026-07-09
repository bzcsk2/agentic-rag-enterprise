from agentic_rag_enterprise.agents.planner import PlannerAgent
from agentic_rag_enterprise.agents.sufficient_context import SufficientContextAgent
from agentic_rag_enterprise.agents.synthesis import SynthesisAgent
from agentic_rag_enterprise.config import settings
from agentic_rag_enterprise.graph.state import AgenticRagState
from agentic_rag_enterprise.retrieval.retriever import Retriever
from agentic_rag_enterprise.schemas import SufficiencyStatus


class AgenticRagRuntime:
    """Minimal bounded Agentic RAG loop.

    This class is intentionally framework-light. The next step is to map each
    method into LangGraph nodes and conditional edges.
    """

    def __init__(self) -> None:
        self.planner = PlannerAgent()
        self.retriever = Retriever()
        self.sca = SufficientContextAgent()
        self.synthesis = SynthesisAgent()

    def run(self, query: str) -> AgenticRagState:
        state = AgenticRagState(user_query=query, normalized_query=query.strip())
        state.plan = self.planner.plan(state.normalized_query)
        state.add_trace("plan", state.plan.model_dump())

        while state.iteration < settings.max_iterations:
            state.iteration += 1
            subquestion = state.plan.subquestions[0]
            if subquestion.question in state.visited_queries:
                state.stop_reason = "visited_query"
                break

            state.visited_queries.add(subquestion.question)
            retrieved = self.retriever.retrieve(
                query=subquestion.question,
                corpus_ids=subquestion.target_corpora,
                top_k=settings.max_retrieval_top_k,
            )
            state.evidence.extend(retrieved)
            state.tool_calls += 1
            state.add_trace("retrieve", {"query": subquestion.question, "count": len(retrieved)})

            decision = self.sca.judge(state.user_query, state.plan, state.evidence)
            state.sufficiency_decisions.append(decision)
            state.add_trace("sufficiency", decision.model_dump())

            if decision.status == SufficiencyStatus.SUFFICIENT:
                state.stop_reason = "sufficient_context"
                break

            if not decision.next_queries:
                state.stop_reason = "no_next_query"
                break

        if state.stop_reason is None:
            state.stop_reason = "max_iterations"

        decision = state.sufficiency_decisions[-1]
        state.final_answer = self.synthesis.synthesize(state.user_query, state.evidence, decision)
        state.add_trace("synthesis", state.final_answer.model_dump())
        return state
