"""E-018 PlanExecutionError — typed exception for fail-closed execution.

Raised when the whole execution fails closed (zero usable Evidence, security binding
failure, or pre-execution validation rejection). Never carries corpus/tenant/user names
in its public message.
"""

from __future__ import annotations


class PlanExecutionError(Exception):
    """Whole-execution failure that cannot produce a usable partial result.

    Attributes:
        message: User-safe description (no corpus/tenant/user names).
        error_code: Machine-readable error category.
        detail: Internal audit detail (not user-safe).
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "execution_failed",
        detail: str = "",
    ) -> None:
        self.error_code = error_code
        self.detail = detail
        super().__init__(message)
