"""E-020 M3 eval report (build plan §14 / M3 exit gate).

Runs the versioned eval dataset through BOTH the M3 iteration loop
(``run_case``) and the M2 single-pass Fast Path baseline (``run_case_baseline``),
computes the offline guards (``false_sufficient``, ``judge_timeout_degradation``,
``citation_coverage``), and emits a machine-readable report — M3 vs M2 delta — to
``evals/data/m3_eval_report.json``. This is the reproducible quality-gain artifact
the M3 exit gate requires (provisional False-Sufficient gate + M2 baseline
comparison).
"""

from __future__ import annotations

import json
from pathlib import Path

from agentic_rag_enterprise.evals.dataset import EvalCase, load_dataset
from agentic_rag_enterprise.evals.metrics import (
    citation_coverage,
    false_sufficient,
    judge_timeout_degradation,
)
from agentic_rag_enterprise.evals.runner import run_case, run_case_baseline

_REPORT_PATH = Path(__file__).resolve().parent / "data" / "m3_eval_report.json"


def _evaluate_case(case: EvalCase) -> dict:
    m3 = run_case(case)
    m2 = run_case_baseline(case)

    fs_m3 = false_sufficient(m3, case.gold_missing_fact_ids)
    fs_m2 = false_sufficient(m2, case.gold_missing_fact_ids)
    jt_m3 = judge_timeout_degradation(m3)
    cc_m3 = citation_coverage(
        [c.evidence_id for c in m3.citations],
        [e.evidence_id for e in m3.evidence],
    )

    return {
        "id": case.id,
        "query": case.query,
        "expected_overall": case.expected_overall,
        "gold_missing_fact_ids": list(case.gold_missing_fact_ids),
        "m3": {
            "overall_status": m3.coverage.overall_status if m3.coverage else None,
            "completeness": m3.completeness,
            "confidence": m3.confidence,
            "abstained": m3.abstained,
            "gap_rounds": m3.gap_rounds,
            "stop_reason": m3.stop_reason,
            "claims": len(m3.claims),
            "false_sufficient": fs_m3.score,
            "judge_timeout_degradation": jt_m3.score,
            "citation_coverage": cc_m3.score,
        },
        "m2_baseline": {
            "completeness": m2.completeness,
            "confidence": m2.confidence,
            "abstained": m2.abstained,
            "false_sufficient": fs_m2.score,
        },
    }


def generate_m3_report(name: str = "m3_v1", *, write: bool = True) -> dict:
    """Generate (and optionally persist) the M3 eval report.

    Returns a machine-readable dict with per-case records and an aggregate
    ``summary`` (M3 vs M2 complete-rate delta, mean guard scores, and the
    provisional False-Sufficient gate result).
    """
    dataset = load_dataset(name)
    cases = [_evaluate_case(c) for c in dataset.cases]

    n = len(cases) or 1
    m3_complete = [c for c in cases if c["m3"]["completeness"] == "complete"]
    m2_complete = [c for c in cases if c["m2_baseline"]["completeness"] == "complete"]
    m3_fs_failures = [c for c in cases if c["m3"]["false_sufficient"] < 1.0]

    summary = {
        "n_cases": len(cases),
        "m3_complete_rate": len(m3_complete) / n,
        "m2_complete_rate": len(m2_complete) / n,
        "complete_rate_delta": len(m3_complete) / n - len(m2_complete) / n,
        "m3_false_sufficient_failures": len(m3_fs_failures),
        "mean_false_sufficient": sum(c["m3"]["false_sufficient"] for c in cases) / n,
        "mean_citation_coverage": sum(c["m3"]["citation_coverage"] for c in cases) / n,
        "provisional_gate_pass": len(m3_fs_failures) == 0,
    }

    report = {
        "version": name,
        "generated_for": "M3 E-019/E-020 quality-iteration exit gate",
        "summary": summary,
        "cases": cases,
    }

    if write:
        _REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> None:  # pragma: no cover - manual CLI entry point
    import sys

    report = generate_m3_report()
    if report["summary"]["provisional_gate_pass"]:
        print("M3 eval report written; provisional False-Sufficient gate: PASS", file=sys.stderr)
    else:
        print(
            "M3 eval report written; provisional False-Sufficient gate: FAIL "
            f"({report['summary']['m3_false_sufficient_failures']} failure(s))",
            file=sys.stderr,
        )


if __name__ == "__main__":  # pragma: no cover
    main()
