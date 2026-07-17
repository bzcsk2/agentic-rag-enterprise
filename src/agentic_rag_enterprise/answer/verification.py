"""E-013 single key-claim support verification (build plan §16.4, MVP slice).

Deterministic, single-pass check — no LLM Judge, no regeneration loop (those
are deferred to E-019/E-020). For each claim we verify its ``evidence_ids``
resolve to the Evidence actually used by the answer; any claim with an
unresolved id is marked ``unsupported`` and removed from the final answer. A
removed *critical* claim is recorded so the builder can downgrade
``completeness`` to ``partial``.
"""

from pydantic import BaseModel, Field

from agentic_rag_enterprise.answer.envelope import Claim


class ClaimVerificationResult(BaseModel):
    """Outcome of the single-pass claim check."""

    kept_claims: list[Claim] = Field(default_factory=list)
    removed_claims: list[Claim] = Field(default_factory=list)
    any_critical_unsupported: bool = False


def verify_claims(
    claims: list[Claim],
    evidence_ids: set[str],
) -> ClaimVerificationResult:
    """Validate that claims bind only to Evidence that was actually used.

    Args:
        claims: The extracted claims (their ``support_status`` is taken as given
            by the upstream extractor unless evidence fails to resolve).
        evidence_ids: The set of Evidence snapshot ids available to the answer.

    Returns:
        A :class:`ClaimVerificationResult` with unsupported claims removed and a
        flag for any removed critical claim.
    """
    kept: list[Claim] = []
    removed: list[Claim] = []
    any_critical_unsupported = False

    for claim in claims:
        unresolved = [eid for eid in claim.evidence_ids if eid not in evidence_ids]
        if unresolved:
            claim = claim.model_copy(update={"support_status": "unsupported"})
            removed.append(claim)
            if claim.importance == "critical":
                any_critical_unsupported = True
            continue
        kept.append(claim)

    return ClaimVerificationResult(
        kept_claims=kept,
        removed_claims=removed,
        any_critical_unsupported=any_critical_unsupported,
    )
