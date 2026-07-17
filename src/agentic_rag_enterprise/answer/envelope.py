"""E-013 typed answer models (build plan §7.9 / §16).

``AnswerEnvelope`` wraps a caller-supplied grounded answer plus its claims and
the Evidence Snapshots those claims cite. The model is validated so its fields
can never contradict one another (mirrors the E-012 validated-model approach):
no dangling citation, and the ``abstained`` state is locked to empty
claims/evidence with ``completeness == insufficient``.

These are the *real* enterprise models — they are deliberately distinct from
the M0 baseline mocks in ``schemas.py`` (``GroundedAnswer`` / ``Evidence``).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentic_rag_enterprise.domain.evidence import Evidence as SnapshotEvidence

ClaimImportance = Literal["critical", "supporting", "minor"]
ClaimSupport = Literal["entailed", "partially_entailed", "contradicted", "unsupported"]
Completeness = Literal["complete", "partial", "insufficient", "conflicted"]
Confidence = Literal["high", "medium", "low"]


class Claim(BaseModel):
    """An atomic claim extracted from the answer (build plan §16.3)."""

    claim_id: str
    text: str
    importance: ClaimImportance = "supporting"
    evidence_ids: list[str] = Field(default_factory=list)
    support_status: ClaimSupport = "entailed"


class Citation(BaseModel):
    """An immutable, resolvable citation to an Evidence Snapshot (§16.5 / §16.6).

    Carries the 1-based UI index plus the snapshot's source coordinates and the
    immutable reference fields so an audit record can replay the exact snapshot
    the claim was grounded on — never a live link to the latest source document.
    """

    index: int
    evidence_id: str

    corpus_id: str
    document_id: str
    document_version: str
    section_path: tuple[str, ...] = Field(default_factory=tuple)
    page_number: int | None = None
    source_uri: str = ""

    text_hash: str
    retrieved_at: str
    policy_version: str


class AnswerEnvelope(BaseModel):
    """Typed, validated grounded-answer container (build plan §7.9).

    Single-corpus / single-iteration MVP slice: ``iterations`` and ``tool_calls``
    are fixed at 1 because E-013 runs on the one-pass Fast Path. The model is
    validated so the following invariants always hold:

    * every ``Claim.evidence_ids`` entry resolves to an ``evidence`` snapshot
      (no dangling citation);
    * ``abstained is True`` ⇒ ``claims == []``, ``evidence == []``,
      ``completeness == insufficient``;
    * ``completeness == insufficient`` ⇒ ``abstained is True``.
    """

    model_config = ConfigDict(frozen=True)

    request_id: str
    session_id: str

    answer_markdown: str

    claims: tuple[Claim, ...] = Field(default_factory=tuple)
    evidence: tuple[SnapshotEvidence, ...] = Field(default_factory=tuple)
    citations: tuple[Citation, ...] = Field(default_factory=tuple)

    completeness: Completeness
    confidence: Confidence

    missing_aspects: tuple[str, ...] = Field(default_factory=tuple)
    limitations: tuple[str, ...] = Field(default_factory=tuple)

    corpora_used: tuple[str, ...] = Field(default_factory=tuple)
    iterations: int = 1
    tool_calls: int = 1

    stop_reason: str
    abstained: bool

    @model_validator(mode="after")
    def _lock_state(self) -> "AnswerEnvelope":
        evidence_ids = {e.evidence_id for e in self.evidence}
        # No dangling citation: every claim's evidence id must resolve.
        for claim in self.claims:
            unknown = [eid for eid in claim.evidence_ids if eid not in evidence_ids]
            if unknown:
                raise ValueError(f"claim {claim.claim_id!r} cites unknown evidence ids: {unknown}")
        # Abstain state is locked.
        if self.abstained:
            if self.claims:
                raise ValueError("abstained envelope must carry no claims")
            if self.evidence:
                raise ValueError("abstained envelope must carry no evidence")
            if self.completeness != "insufficient":
                raise ValueError("abstained envelope completeness must be 'insufficient'")
        if self.completeness == "insufficient" and not self.abstained:
            raise ValueError("completeness 'insufficient' requires abstained=True")
        return self
