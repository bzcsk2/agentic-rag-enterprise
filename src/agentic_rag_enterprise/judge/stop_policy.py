"""E-020 iteration Stop Policy (build plan §14.5 / §14.6).

Decides whether the gap-retrieval loop should stop. Hard stops (§14.5): reaching
``max_rounds``, a Judge failure/timeout, exhausted budget, or an overall
``sufficient`` verdict. Information stops: two consecutive rounds that add no new
Evidence id AND no newly covered fact (``no_new_evidence``, §14.6), or nothing
left to retrieve (``all_sources_exhausted``). The loop must never run unbounded.

The "new evidence" signal is NOT id-only (build plan §14.6): a round counts as a
gain when it yields a new Evidence id, a newly covered fact, OR genuinely new
content (a new document version / new text hash). The policy tracks consecutive
no-gain rounds as per-instance state so ``no_new_evidence`` only fires after two
consecutive such rounds.
"""

from __future__ import annotations

from agentic_rag_enterprise.judge.models import StopDecision


class StopPolicy:
    """Bounded-iteration stop policy (stateful for one ``answer_with_iteration`` call)."""

    name = "deterministic"

    def __init__(self) -> None:
        self._no_gain = 0

    def decide(
        self,
        *,
        round: int,
        max_rounds: int,
        overall_status: str | None,
        can_continue: bool,
        new_evidence_ids: set[str],
        new_covered_fact_ids: set[str],
        judge_ok: bool = True,
        budget_remaining: float = 1.0,
        new_content: bool = False,
    ) -> StopDecision:
        """Return a stop decision for the current round.

        Args:
            round: 0-based index of the round just completed.
            max_rounds: inclusive cap on rounds performed (default 3).
            overall_status: the Coverage Judge's overall verdict this round.
            can_continue: whether any fact is still missing/partially_supported.
            new_evidence_ids: Evidence ids retrieved this round not seen before.
            new_covered_fact_ids: required-fact ids that became covered this round.
            judge_ok: False if the judge failed/timed out (degrade conservatively).
            budget_remaining: simple remaining budget in [0, 1]; <=0 means exhausted.
            new_content: True when this round yielded genuinely new content even if
                no new Evidence id appeared — a new document version or a new text
                hash (build plan §14.6). Treated as a gain.
        """
        if not judge_ok:
            return StopDecision(
                should_stop=True,
                reason="tool_unavailable",
                explanation="judge failed or timed out; degrading conservatively",
            )
        if budget_remaining <= 0:
            return StopDecision(
                should_stop=True,
                reason="budget_exhausted",
                explanation="iteration budget exhausted",
            )
        if overall_status == "sufficient":
            return StopDecision(
                should_stop=True, reason="sufficient", explanation="all required facts covered"
            )
        if not can_continue:
            return StopDecision(
                should_stop=True,
                reason="all_sources_exhausted",
                explanation="no facts left to retrieve for",
            )

        # Gain accounting (build plan §14.6): a round is a gain if it produces a
        # new Evidence id, a newly covered fact, or genuinely new content.
        gained = bool(new_evidence_ids) or bool(new_covered_fact_ids) or new_content
        if gained:
            self._no_gain = 0
        else:
            self._no_gain += 1

        # Information stop: two consecutive no-gain rounds (§14.5 / §14.6 spirit).
        if self._no_gain >= 2:
            return StopDecision(
                should_stop=True,
                reason="no_new_evidence",
                explanation="no new evidence or covered fact for two consecutive rounds",
            )

        # Hard iteration cap (still a hard stop; cannot run unbounded).
        if round + 1 >= max_rounds:
            return StopDecision(
                should_stop=True,
                reason="max_rounds",
                explanation=f"reached max_rounds={max_rounds}",
            )

        return StopDecision(
            should_stop=False,
            reason="continue",
            explanation="gaps remain and new evidence was found",
        )
