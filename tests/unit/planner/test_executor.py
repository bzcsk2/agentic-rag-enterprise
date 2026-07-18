"""Unit tests for PlanExecutor (contract §11 acceptance matrix).

Uses mock Tools and registries to verify DAG scheduling, budget, retry, and
failure degradation without requiring real SecureRetriever or Qdrant.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from agentic_rag_enterprise.corpus.registry import InMemoryCorpusRegistry
from agentic_rag_enterprise.domain.security import SecurityContext
from agentic_rag_enterprise.planner.errors import PlanExecutionError
from agentic_rag_enterprise.planner.executor import PlanExecutor
from agentic_rag_enterprise.planner.models import (
    OutputSchemaId,
    PlanStep,
    QueryPlan,
)
from agentic_rag_enterprise.planner.result import StepStatus
from agentic_rag_enterprise.planner.tool_registry import (
    Tool,
    ToolSpec,
    TypedStepOutput,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(**kw: Any) -> SecurityContext:
    base = dict(
        request_id="r",
        session_id="s",
        tenant_id="local",
        user_id="u",
        policy_version="1.0",
    )
    base.update(kw)
    return SecurityContext(**base)


def _step(**kw: Any) -> PlanStep:
    base = dict(
        step_id="s1",
        step_type="retrieve",
        description="d",
        target_corpus_ids=("engineering_wiki",),
        capability_id="vector_search",
        query="test query",
        output_schema_id="entity",
        max_tool_calls=2,
    )
    base.update(kw)
    return PlanStep(**base)


# ---------------------------------------------------------------------------
# Mock Tool
# ---------------------------------------------------------------------------


class _MockTool:
    """A Tool whose execute_step returns a fixed output."""

    def __init__(
        self,
        outputs: dict[str, object] | None = None,
        evidence_ids: tuple[str, ...] = (),
        schema_id: OutputSchemaId = "entity",
        raise_exc: type[Exception] | None = None,
        raise_on_attempt: int | None = None,
    ) -> None:
        self._outputs = outputs or {"text": "mock"}
        self._evidence_ids = evidence_ids
        self._schema_id = schema_id
        self._raise_exc = raise_exc
        self._raise_on_attempt = raise_on_attempt
        self.call_count = 0

    def execute_step(
        self,
        step: PlanStep,
        resolved_inputs: Mapping[str, object],
        ctx: SecurityContext,
    ) -> TypedStepOutput:
        self.call_count += 1
        if self._raise_exc is not None:
            if self._raise_on_attempt is None or self.call_count <= self._raise_on_attempt:
                raise self._raise_exc("mock error")
        return TypedStepOutput(
            outputs=self._outputs,
            evidence_ids=self._evidence_ids,
            schema_id=self._schema_id,
        )


# ---------------------------------------------------------------------------
# Mock ToolRegistry & ToolSpec
# ---------------------------------------------------------------------------


def _make_tool_spec(
    output_models: Mapping[OutputSchemaId, type[BaseModel]] | None = None,
) -> ToolSpec:
    class _DummyInput(BaseModel):
        model_config = ConfigDict(frozen=True)
        query: str = "default"

    return ToolSpec(
        step_type="retrieve",
        capability_id="vector_search",
        input_model=_DummyInput,
        output_models=output_models or {},
        retryable_errors=frozenset(),
    )


class _MockToolRegistry:
    def __init__(self, tool: Tool, spec: ToolSpec | None = None) -> None:
        self._tool = tool
        self._spec = spec or _make_tool_spec()

    def get(self, step_type: str, capability_id: str) -> tuple[Tool, ToolSpec]:
        return (self._tool, self._spec)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_happy_path_single_step() -> None:
    """A single step executes successfully and returns evidence_ids."""
    tool = _MockTool(evidence_ids=("ev1",))
    registry = _MockToolRegistry(tool)
    executor = PlanExecutor(registry)

    plan = QueryPlan(
        plan_id="p1",
        task_type="t",
        max_iterations=1,
        max_tool_calls=10,
        steps=(_step(step_id="s1"),),
    )
    result = executor.execute(plan, _ctx(), InMemoryCorpusRegistry())

    assert result.accepted is True
    assert result.executed is True
    assert result.degraded is False
    assert len(result.steps) == 1
    assert result.steps[0].status == StepStatus.succeeded
    assert result.steps[0].tool_calls_consumed == 1
    assert result.evidence_ids == ("ev1",)
    assert tool.call_count == 1


def test_two_independent_steps_parallel() -> None:
    """Two independent steps both succeed."""
    tool = _MockTool(evidence_ids=("ev1",))
    # We use the same mock for both steps (it gets called twice).
    registry = _MockToolRegistry(tool)
    executor = PlanExecutor(registry, concurrency=2)

    plan = QueryPlan(
        plan_id="p1",
        task_type="t",
        max_iterations=1,
        max_tool_calls=10,
        steps=(
            _step(step_id="s1", target_corpus_ids=("engineering_wiki",)),
            _step(step_id="s2", target_corpus_ids=("product_docs",)),
        ),
    )
    result = executor.execute(plan, _ctx(), InMemoryCorpusRegistry())

    assert result.accepted is True
    assert len(result.steps) == 2
    assert all(s.status == StepStatus.succeeded for s in result.steps)
    assert tool.call_count == 2


def test_required_dependency_skipped_downstream() -> None:
    """A failed required upstream -> downstream is skipped_dependency.
    An independent third step with evidence still succeeds (degraded result)."""
    # Step s1 fails (via ValueErrror from the tool), s2 depends on s1,
    # s3 is independent and succeeds.
    call_log: list[str] = []

    class _FailFirstTool:
        def execute_step(
            self,
            step: PlanStep,
            resolved_inputs: Mapping[str, object],
            ctx: SecurityContext,
        ) -> TypedStepOutput:
            call_log.append(step.step_id)
            if step.step_id == "s1":
                raise ValueError("programming bug")
            return TypedStepOutput(
                outputs={"text": "ok"},
                evidence_ids=("ev3",),
                schema_id=step.output_schema_id,
            )

    exec_spec = _make_tool_spec()
    exec_spec_fixed = ToolSpec(
        step_type="retrieve",
        capability_id="vector_search",
        input_model=exec_spec.input_model,
        output_models=exec_spec.output_models,
        retryable_errors=frozenset({ConnectionError}),
    )

    class _FixedRegistry:
        def get(self, step_type: str, capability_id: str) -> tuple[Tool, ToolSpec]:
            return (_FailFirstTool(), exec_spec_fixed)

    executor = PlanExecutor(_FixedRegistry(), concurrency=2)

    plan = QueryPlan(
        plan_id="p1",
        task_type="t",
        max_iterations=1,
        max_tool_calls=10,
        steps=(
            _step(
                step_id="s1",
                capability_id="vector_search",
                max_tool_calls=1,
            ),
            _step(
                step_id="s2",
                depends_on_step_ids=("s1",),
                query="dep query",
            ),
            _step(
                step_id="s3",
                target_corpus_ids=("product_docs",),
                query="independent query",
            ),
        ),
    )
    result = executor.execute(plan, _ctx(), InMemoryCorpusRegistry())

    assert len(result.steps) == 3
    assert result.steps[0].status == StepStatus.failed  # s1 failed
    assert result.steps[1].status == StepStatus.skipped_dependency  # s2 skipped
    assert result.steps[2].status == StepStatus.succeeded  # s3 succeeded
    assert result.degraded is True
    assert result.evidence_ids == ("ev3",)


def test_retry_on_retryable_error() -> None:
    """A retryable error triggers a second attempt."""
    call_log: list[int] = []

    class _RetryTool:
        def execute_step(
            self,
            step: PlanStep,
            resolved_inputs: Mapping[str, object],
            ctx: SecurityContext,
        ) -> TypedStepOutput:
            call_log.append(len(call_log) + 1)
            if len(call_log) == 1:
                raise ConnectionError("transient")
            return TypedStepOutput(
                outputs={"text": "retried"},
                evidence_ids=("ev1",),
                schema_id=step.output_schema_id,
            )

    spec = ToolSpec(
        step_type="retrieve",
        capability_id="vector_search",
        input_model=_make_tool_spec().input_model,
        output_models={},
        retryable_errors=frozenset({ConnectionError}),
    )

    class _SimpleRegistry:
        def get(self, step_type: str, capability_id: str) -> tuple[Tool, ToolSpec]:
            return (_RetryTool(), spec)

    executor = PlanExecutor(_SimpleRegistry(), concurrency=1)

    plan = QueryPlan(
        plan_id="p1",
        task_type="t",
        max_iterations=1,
        max_tool_calls=10,
        steps=(_step(step_id="s1", max_tool_calls=2),),
    )
    result = executor.execute(plan, _ctx(), InMemoryCorpusRegistry())

    assert len(call_log) == 2  # two calls (initial + retry)
    assert result.steps[0].status == StepStatus.succeeded
    assert result.steps[0].attempts == 2
    assert result.steps[0].tool_calls_consumed == 2  # 1 per attempt


def test_no_retry_on_programming_error() -> None:
    """ValueError is never retried."""
    tool = _MockTool(raise_exc=ValueError("bug"))
    spec = _make_tool_spec()
    spec = ToolSpec(
        step_type="retrieve",
        capability_id="vector_search",
        input_model=spec.input_model,
        output_models=spec.output_models,
        retryable_errors=frozenset({ConnectionError}),
    )
    registry = _MockToolRegistry(tool, spec)
    executor = PlanExecutor(registry, concurrency=1)

    plan = QueryPlan(
        plan_id="p1",
        task_type="t",
        max_iterations=1,
        max_tool_calls=10,
        steps=(_step(step_id="s1", max_tool_calls=2),),
    )

    with pytest.raises(PlanExecutionError):
        executor.execute(plan, _ctx(), InMemoryCorpusRegistry())


def test_max_tool_calls_one_blocks_retry() -> None:
    """max_tool_calls=1 prevents any retry even on retryable error."""
    tool = _MockTool(
        raise_exc=ConnectionError("transient"),
        raise_on_attempt=1,
    )
    spec = _make_tool_spec()
    spec = ToolSpec(
        step_type="retrieve",
        capability_id="vector_search",
        input_model=spec.input_model,
        output_models=spec.output_models,
        retryable_errors=frozenset({ConnectionError}),
    )
    registry = _MockToolRegistry(tool, spec)
    executor = PlanExecutor(registry, concurrency=1)

    plan = QueryPlan(
        plan_id="p1",
        task_type="t",
        max_iterations=1,
        max_tool_calls=10,
        steps=(_step(step_id="s1", max_tool_calls=1),),
    )

    with pytest.raises(PlanExecutionError):
        executor.execute(plan, _ctx(), InMemoryCorpusRegistry())

    assert tool.call_count == 1  # only one attempt


def test_evidence_ids_first_occurrence_dedup() -> None:
    """evidence_ids dedup preserves first occurrence order."""
    tool = _MockTool(evidence_ids=("ev_a", "ev_b", "ev_a"))
    registry = _MockToolRegistry(tool)
    executor = PlanExecutor(registry, concurrency=1)

    plan = QueryPlan(
        plan_id="p1",
        task_type="t",
        max_iterations=1,
        max_tool_calls=10,
        steps=(_step(step_id="s1"),),
    )
    result = executor.execute(plan, _ctx(), InMemoryCorpusRegistry())

    # "ev_a" appears twice in the tool output but should only appear once in result.
    assert result.evidence_ids == ("ev_a", "ev_b")


def test_budget_exhaustion() -> None:
    """When budget runs out, subsequent steps get budget_exhausted."""
    tool = _MockTool(evidence_ids=("ev1",))
    spec = _make_tool_spec()
    registry = _MockToolRegistry(tool, spec)
    executor = PlanExecutor(registry, concurrency=1)

    plan = QueryPlan(
        plan_id="p1",
        task_type="t",
        max_iterations=1,
        max_tool_calls=1,  # only 1 unit for 2 steps
        steps=(
            _step(step_id="s1", max_tool_calls=1),
            _step(step_id="s2", max_tool_calls=1, target_corpus_ids=("product_docs",)),
        ),
    )

    with pytest.raises(PlanExecutionError):
        executor.execute(plan, _ctx(), InMemoryCorpusRegistry())


def test_zero_usable_evidence_raises() -> None:
    """When no step produces evidence, PlanExecutionError is raised."""
    tool = _MockTool(evidence_ids=())  # no evidence
    registry = _MockToolRegistry(tool)
    executor = PlanExecutor(registry, concurrency=1)

    plan = QueryPlan(
        plan_id="p1",
        task_type="t",
        max_iterations=1,
        max_tool_calls=10,
        steps=(_step(step_id="s1"),),
    )

    with pytest.raises(PlanExecutionError, match="no step produced usable evidence"):
        executor.execute(plan, _ctx(), InMemoryCorpusRegistry())


def test_plan_rejected_raises() -> None:
    """An invalid plan raises PlanExecutionError immediately (zero Tools)."""
    tool = _MockTool()
    registry = _MockToolRegistry(tool)
    executor = PlanExecutor(registry, concurrency=1)

    # Plan with no steps AND no query — validator will reject.
    plan = QueryPlan(
        plan_id="p1",
        task_type="t",
        max_iterations=1,
        max_tool_calls=10,
        steps=(_step(step_id="s1", query=None, query_template=None),),
    )

    with pytest.raises(PlanExecutionError, match="plan failed pre-execution validation"):
        executor.execute(plan, _ctx(), InMemoryCorpusRegistry())

    assert tool.call_count == 0  # zero Tools launched
