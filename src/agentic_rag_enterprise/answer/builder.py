"""E-013 AnswerEnvelope builder (build plan §7.9 / §16 / §14.7).

Wraps a caller-supplied grounded answer (``answer_markdown`` + ``claims``) into
a typed, validated :class:`AnswerEnvelope`, rendering immutable citations from
the E-011 Evidence Snapshots and running the single deterministic key-claim
support check. When the E-012 Fast Path says ``insufficient`` it produces a
conservative refusal envelope with no fabricated facts.
"""

from agentic_rag_enterprise.answer.citations import render_citations
from agentic_rag_enterprise.answer.envelope import (
    AnswerEnvelope,
    Claim,
    Completeness,
    Confidence,
)
from agentic_rag_enterprise.answer.verification import verify_claims
from agentic_rag_enterprise.domain.security import SecurityContext
from agentic_rag_enterprise.retrieval.fast_path import (
    FastPathResult,
    FastPathSufficiency,
)

# Conservative refusal wording (build plan §16.2): states missing info, reveals
# no document name or content, fabricates nothing.
_ABSTAIN_MESSAGE = (
    "I cannot answer this reliably: no authorized evidence was found for your question."
)


def build_answer_envelope(
    fast_path_result: FastPathResult,
    ctx: SecurityContext,
    *,
    answer_markdown: str,
    claims: list[Claim] | None = None,
) -> AnswerEnvelope:
    """Build a validated envelope from a Fast Path result and a grounded answer.

    Args:
        fast_path_result: The E-012 one-pass decision (carries the Evidence and
            the ``should_abstain`` signal).
        ctx: The runtime-injected security context (supplies ``request_id`` /
            ``session_id``).
        answer_markdown: The caller-supplied grounded answer text. E-013 does
            NOT generate it (LLM synthesis is wired by the E-014 service).
        claims: The caller-supplied atomic claims to verify and cite.

    Returns:
        A frozen, validated :class:`AnswerEnvelope`. On the ``insufficient``
        branch a conservative refusal envelope is returned instead.
    """
    if fast_path_result.sufficiency is FastPathSufficiency.INSUFFICIENT:
        return conservative_refusal(fast_path_result, ctx)

    evidence = fast_path_result.evidence
    evidence_ids = {ev.evidence_id for ev in evidence}

    verification = verify_claims(claims or [], evidence_ids)
    citations = render_citations(evidence)

    if verification.removed_claims:
        completeness: Completeness = "partial"
        confidence: Confidence = "medium"
    else:
        completeness = "complete"
        confidence = "high"

    return AnswerEnvelope(
        request_id=ctx.request_id,
        session_id=ctx.session_id,
        answer_markdown=answer_markdown,
        claims=tuple(verification.kept_claims),
        evidence=tuple(evidence),
        citations=tuple(citations),
        completeness=completeness,
        confidence=confidence,
        corpora_used=(fast_path_result.corpus_id,),
        iterations=1,
        tool_calls=1,
        stop_reason=fast_path_result.stop_reason.value,
        abstained=False,
    )


def conservative_refusal(
    fast_path_result: FastPathResult,
    ctx: SecurityContext,
) -> AnswerEnvelope:
    """Build an abstained refusal envelope for an ``insufficient`` Fast Path result."""
    return AnswerEnvelope(
        request_id=ctx.request_id,
        session_id=ctx.session_id,
        answer_markdown=_ABSTAIN_MESSAGE,
        claims=(),
        evidence=(),
        citations=(),
        completeness="insufficient",
        confidence="low",
        corpora_used=(fast_path_result.corpus_id,),
        iterations=1,
        tool_calls=1,
        stop_reason=fast_path_result.stop_reason.value,
        abstained=True,
    )
