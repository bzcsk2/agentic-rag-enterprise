"""E-013 citation rendering (build plan §16.5 / §16.6).

Renders immutable, resolvable citations from E-011 Evidence Snapshots. Each
citation carries the snapshot's source coordinates plus the immutable reference
fields (``document_version``, ``text_hash``, ``retrieved_at``, ``policy_version``)
so an audit record replays the exact snapshot a claim was grounded on — never a
live link to the latest source document.
"""

from agentic_rag_enterprise.answer.envelope import Citation
from agentic_rag_enterprise.domain.evidence import Evidence as SnapshotEvidence


def render_citations(
    evidence: list[SnapshotEvidence] | tuple[SnapshotEvidence, ...],
) -> list[Citation]:
    """Render one immutable :class:`Citation` per Evidence Snapshot, 1-based indexed.

    Order is stable (insertion order of ``evidence``), which is what the UI
    ``[n]`` markers reference.
    """
    citations: list[Citation] = []
    for index, ev in enumerate(evidence, start=1):
        citations.append(
            Citation(
                index=index,
                evidence_id=ev.evidence_id,
                corpus_id=ev.corpus_id,
                document_id=ev.document_id,
                document_version=ev.document_version,
                section_path=tuple(ev.section_path),
                page_number=ev.page_number,
                source_uri=ev.source_uri,
                text_hash=ev.text_hash,
                retrieved_at=ev.retrieved_at.isoformat()
                if hasattr(ev.retrieved_at, "isoformat")
                else str(ev.retrieved_at),
                policy_version=ev.policy_version,
            )
        )
    return citations


def format_citation_panel(citations: list[Citation]) -> str:
    """Render the UI citation panel (build plan §16.5), e.g. ``[1] corpus / doc …``."""
    lines: list[str] = ["来源"]
    for cit in citations:
        section = " / ".join(cit.section_path) if cit.section_path else ""
        parts = [cit.corpus_id, cit.document_id]
        if section:
            parts.append(section)
        if cit.page_number is not None:
            parts.append(f"p.{cit.page_number}")
        lines.append(f"[{cit.index}] {' / '.join(parts)}")
    return "\n".join(lines)
