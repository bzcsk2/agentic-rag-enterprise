"""Operational wrapper: E-022 index migration (build v2 + switch / rollback).

Builds a parallel ``v2`` Qdrant collection from existing child-chunk content,
then atomically flips the retrieval pointer to it (retaining the old collection
for rollback). The previous collection is never cleared-and-rebuilt.

Examples
--------
    # Build v2 and switch retrieval to it:
    python scripts/rebuild_index.py --corpus engineering_wiki \\
        --embedding-version v2 --chunking-version v1

    # Build only, do not switch yet (offline eval / shadow retrieval first):
    python scripts/rebuild_index.py --corpus engineering_wiki --no-switch

    # Roll retrieval back to the retained previous collection:
    python scripts/rebuild_index.py --corpus engineering_wiki --rollback
"""

from __future__ import annotations

import argparse

from agentic_rag_enterprise.ingestion.index_migration import (
    build_index_v2,
    rollback_index,
    switch_index,
)
from agentic_rag_enterprise.services.container import DENSE_DIM, get_default_container


def main() -> None:
    parser = argparse.ArgumentParser(
        description="E-022 index migration: build v2 + switch / rollback"
    )
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--embedding-version", default="v2")
    parser.add_argument("--chunking-version", default="v1")
    parser.add_argument(
        "--no-switch", action="store_true", help="build only; do not flip the pointer"
    )
    parser.add_argument(
        "--rollback", action="store_true", help="flip pointer back to retained collection"
    )
    parser.add_argument("--dry-run", action="store_true", help="report without mutating")
    args = parser.parse_args()

    container = get_default_container()
    # build_index_v2 needs the encoders; switch_index/rollback_index do not.
    build_kwargs = dict(
        metadata_store=container.metadata_store,
        vector_store=container.vector_store,
        corpus_registry=container.corpus_registry,
        dense_encoder=container.document_manager._dense,
        sparse_encoder=container.document_manager._sparse,
    )
    pointer_kwargs = dict(
        metadata_store=container.metadata_store,
        vector_store=container.vector_store,
        corpus_registry=container.corpus_registry,
    )

    if args.rollback:
        previous = rollback_index(args.corpus, **pointer_kwargs)
        print(f"rolled back {args.corpus} -> {previous}")
        return

    collection = build_index_v2(
        args.corpus,
        embedding_version=args.embedding_version,
        chunking_version=args.chunking_version,
        dense_size=DENSE_DIM,
        **build_kwargs,
    )
    print(f"built collection {collection}")

    if args.no_switch:
        print("pointer NOT switched (--no-switch); switch manually after eval")
        return

    switch_index(
        args.corpus,
        target_collection=collection,
        dry_run=args.dry_run,
        **pointer_kwargs,
    )
    print(f"switched {args.corpus} -> {collection}")


if __name__ == "__main__":
    main()
