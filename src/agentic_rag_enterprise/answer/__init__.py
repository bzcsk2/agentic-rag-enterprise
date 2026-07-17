"""E-013 answer package: AnswerEnvelope, citation rendering, key-claim verification.

Builds on the E-012 Fast Path result and the E-011 Evidence Snapshot. Does NOT
perform LLM answer synthesis (that is wired by the E-014 application service).
"""

from agentic_rag_enterprise.answer.builder import (
    build_answer_envelope,
    conservative_refusal,
)
from agentic_rag_enterprise.answer.citations import (
    format_citation_panel,
    render_citations,
)
from agentic_rag_enterprise.answer.envelope import (
    AnswerEnvelope,
    Citation,
    Claim,
)
from agentic_rag_enterprise.answer.verification import (
    ClaimVerificationResult,
    verify_claims,
)

__all__ = [
    "AnswerEnvelope",
    "Claim",
    "Citation",
    "render_citations",
    "format_citation_panel",
    "verify_claims",
    "ClaimVerificationResult",
    "build_answer_envelope",
    "conservative_refusal",
]
