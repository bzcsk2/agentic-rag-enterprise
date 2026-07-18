"""E-020 eval metrics (build plan §14 / M3).

Metric functions take a produced :class:`AnswerEnvelope` (and, where relevant,
gold labels) and return an :class:`EvalResult` with a ``score`` in ``[0, 1]``
(1.0 = good) plus machine-readable ``details``. These are the offline guards that
catch the two failure modes the M3 iteration loop is specifically meant to
prevent: falsely reporting ``complete`` when a required fact is uncovered, and
presenting a confident fabricated answer when the judge itself fails.
"""

from agentic_rag_enterprise.answer.envelope import AnswerEnvelope
from agentic_rag_enterprise.judge.query_fact_extractor import make_required_fact
from pydantic import BaseModel


class EvalResult(BaseModel):
    name: str
    score: float
    details: dict = {}


def citation_coverage(answer_citations: list[str], required_evidence_ids: list[str]) -> EvalResult:
    """Measure whether required evidence ids appear in the answer citation map."""
    if not required_evidence_ids:
        return EvalResult(
            name="citation_coverage", score=1.0, details={"reason": "no required ids"}
        )

    covered = set(answer_citations) & set(required_evidence_ids)
    score = len(covered) / len(set(required_evidence_ids))
    return EvalResult(
        name="citation_coverage",
        score=score,
        details={"covered": sorted(covered), "required": required_evidence_ids},
    )


def false_sufficient(
    envelope: AnswerEnvelope,
    gold_missing_fact_ids: list[str],
) -> EvalResult:
    """Guard against a falsely ``complete`` answer that hides a missing fact.

    This is the M3 exit-gate guard that catches the failure mode §14.2 forbids
    ("partial information must not be marked fully supported"): a ``complete``
    answer when the gold/standard answer expects a required fact to be uncovered.

    Two complementary checks (build plan §14 / M3 acceptance P1-5):

    1. **Real judge-error detection (primary).** If the envelope reports
       ``completeness == "complete"`` but ``gold_missing_fact_ids`` is non-empty,
       the answer is a False Sufficient *regardless* of what the system's own
       coverage says. This catches the case the old metric missed: gold says a
       fact is missing, the Coverage Judge wrongly marked it ``supported``, and
       the envelope came back ``complete``.
    2. **Independent coverage cross-check.** Gold fact references are resolved to
       their canonical ids (``make_required_fact``) and intersected with the
       coverage's own ``missing`` / ``contradicted`` sets, so a description-based
       gold label lines up with the ``fact_<sha>`` ids the runner/coverage use
       (the dataset keeps human-readable descriptions; conversion is at metric
       time — no dataset rewrite required).

    Args:
        envelope: The produced answer envelope (must carry ``coverage``).
        gold_missing_fact_ids: Fact references (descriptions or ids) the gold /
            standard answer expects to be uncovered for this query (i.e. the
            answer should NOT be ``complete``).
    """
    if envelope.coverage is None:
        return EvalResult(
            name="false_sufficient", score=1.0, details={"reason": "no coverage attached"}
        )
    if envelope.completeness == "complete" and gold_missing_fact_ids:
        # Primary guard: a `complete` answer while gold expects a missing fact is
        # a False Sufficient (the judge may have wrongly marked the fact supported).
        return EvalResult(
            name="false_sufficient",
            score=0.0,
            details={
                "fired": True,
                "reason": "complete answer while gold expects a missing fact",
                "completeness": envelope.completeness,
                "gold_missing": sorted(gold_missing_fact_ids),
            },
        )
    if envelope.completeness != "complete":
        return EvalResult(
            name="false_sufficient",
            score=1.0,
            details={"reason": "not complete", "completeness": envelope.completeness},
        )

    # Complete with no gold-missing fact: cross-check the system's own coverage
    # against gold (id-resolved), as an independent guard.
    gold_ids = {make_required_fact(g).fact_id for g in gold_missing_fact_ids}
    uncovered = set(envelope.coverage.missing_fact_ids) | set(
        envelope.coverage.contradicted_fact_ids
    )
    fired = bool(gold_ids & uncovered)
    return EvalResult(
        name="false_sufficient",
        score=0.0 if fired else 1.0,
        details={
            "fired": fired,
            "uncovered": sorted(uncovered),
            "gold_missing": sorted(gold_missing_fact_ids),
        },
    )


def judge_timeout_degradation(envelope: AnswerEnvelope) -> EvalResult:
    """Guard that a judge fault degrades conservatively, never a fabricated answer.

    When the Coverage Judge raises (e.g. ``JudgeTimeoutError``), the service must
    not return a confidently ``complete`` answer built on unverified coverage. A
    degraded answer is one whose ``completeness`` is anything other than
    ``"complete"`` (``partial`` / ``insufficient`` / ``conflicted``) or that has
    ``abstained is True``.

    Args:
        envelope: The produced answer envelope after a simulated judge fault.
    """
    degraded = envelope.abstained or envelope.completeness != "complete"
    return EvalResult(
        name="judge_timeout_degradation",
        score=1.0 if degraded else 0.0,
        details={
            "degraded": degraded,
            "completeness": envelope.completeness,
            "abstained": envelope.abstained,
        },
    )
