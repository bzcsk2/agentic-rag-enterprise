"""E-018 execution result models (build plan §13.4, contract §2 / §2a).

Frozen, validated models that capture the terminal state of a single step
(:class:`StepResult`) and the overall plan execution (:class:`PlanExecutionResult`).
`PlanExecutionResult` carries **no** whole-execution ``error_code``/``message`` —
fail-closed results are communicated exclusively via :class:`PlanExecutionError`.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class StepStatus(str, Enum):
    """Terminal or in-flight status of a single DAG step."""

    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    timed_out = "timed_out"
    skipped_dependency = "skipped_dependency"
    budget_exhausted = "budget_exhausted"


class StepResult(BaseModel):
    """Immutable outcome of a single step execution.

    See contract §2 for invariant rules.
    """

    model_config = ConfigDict(frozen=True)

    step_id: str
    status: StepStatus

    # Only meaningful on ``succeeded``; otherwise MUST be empty.
    outputs: dict[str, object] = Field(default_factory=dict)
    evidence_ids: tuple[str, ...] = Field(default_factory=tuple)

    error_code: str | None = None  # e.g. "retrieval_backend_error", "binding_error"
    message: str = ""  # USER-SAFE (never corpus/tenant/user names)
    detail: str = Field(default="", exclude=True, repr=False)  # internal only

    attempts: int = 0  # 1 = initial, 2 = initial + 1 retry
    # Budget units actually consumed by this step (N × attempts for multi-corpus).
    tool_calls_consumed: int = 0


class PlanExecutionResult(BaseModel):
    """Final report for a usable (possibly degraded) plan execution.

    See contract §2a.  **Never** produced for fail-closed results — those raise
    :class:`PlanExecutionError`.  Consequently no ``error_code`` or ``message``
    fields exist on this model.
    """

    model_config = ConfigDict(frozen=True)

    plan_id: str

    # Plan passed pre-execution validation.
    accepted: bool
    # At least one Tool launch was attempted.
    executed: bool
    # Partial success (usable but not all steps succeeded).
    degraded: bool

    steps: tuple[StepResult, ...]  # deterministic plan / topological order
    tool_calls_used: int  # == sum of StepResult.tool_calls_consumed
    # Deduplicated union in first-occurrence topological order.
    evidence_ids: tuple[str, ...] = Field(default_factory=tuple)

    limitations: tuple[str, ...] = Field(default_factory=tuple)  # user-safe
    detail: str = Field(default="", exclude=True, repr=False)  # internal only
