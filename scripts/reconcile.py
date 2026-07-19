"""Operational wrapper: run the E-022 reconciler.

Reconciles a corpus's Qdrant / Parent Store data planes toward the Metadata DB
truth (orphan purge, missing-data-plane rebuild, post-commit cleanup retry,
dead-letter cleanup). Dry-run by default so operators can inspect findings
before mutating.

Example
-------
    python scripts/reconcile.py --all
    python scripts/reconcile.py --corpus engineering_wiki --dry-run
"""

from __future__ import annotations

import argparse

from agentic_rag_enterprise.ingestion.reconciler import Reconciler
from agentic_rag_enterprise.services.container import get_default_container


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconcile corpus data planes toward Metadata DB truth"
    )
    parser.add_argument("--corpus", help="reconcile a single corpus id")
    parser.add_argument("--all", action="store_true", help="reconcile every registered corpus")
    parser.add_argument("--dry-run", action="store_true", help="report findings without mutating")
    args = parser.parse_args()

    container = get_default_container()
    reconciler = Reconciler(
        metadata_store=container.metadata_store,
        vector_store=container.vector_store,
        parent_store=container.parent_store,
        corpus_registry=container.corpus_registry,
        dry_run=args.dry_run,
        purge_document=container.document_manager.reconcile_purge,
        rebuild_document=container.document_manager.rebuild_document,
    )

    if args.corpus:
        reports = [reconciler.reconcile_corpus(args.corpus)]
    else:
        reports = reconciler.reconcile_all()
        if not reports:
            print("no corpora registered")
            return

    for report in reports:
        print(f"corpus={report.corpus_id} run={report.run_id} mutated={report.mutated}")
        if not report.findings:
            print("  no findings")
        for f in report.findings:
            loc = f.document_id or "-"
            print(f"  [{f.kind}] {loc} {f.detail}")


if __name__ == "__main__":
    main()
