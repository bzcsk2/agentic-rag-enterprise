"""Unit tests for the E-022 Reconciler.

Hermetic: in-memory SQLite + in-memory Qdrant + Fake encoders. Verifies orphan
purge, missing-data-plane rebuild, post-commit cleanup retry, dry-run safety,
and per-corpus lease fencing.
"""

import os
import tempfile

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, SparseVector

from agentic_rag_enterprise.corpus.registry import InMemoryCorpusRegistry
from agentic_rag_enterprise.domain.corpus import CorpusConfig
from agentic_rag_enterprise.ingestion.chunker import ParentChildChunker
from agentic_rag_enterprise.ingestion.job import DocumentManager, IngestionRequest
from agentic_rag_enterprise.ingestion.reconciler import Reconciler
from agentic_rag_enterprise.security.policy import ResourceAcl
from agentic_rag_enterprise.storage.metadata_store import MetadataStore
from agentic_rag_enterprise.storage.parent_store import ParentStore
from agentic_rag_enterprise.storage.vector_store import VectorStore, child_point_id

from tests.fixtures import (
    DENSE_DIM,
    FakeDenseEncoder,
    FakeSparseEncoder,
    SAMPLE_MARKDOWN,
    acl_payload,
    make_security_context,
)

from datetime import datetime, timezone

_TS = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _corpus_config() -> CorpusConfig:
    return CorpusConfig(
        corpus_id="eng",
        tenant_id="t1",
        name="eng",
        description="",
        domain="wiki",
        owner="o",
        source_type="wiki",
        capability_ids=["retrieval"],
        security_policy_id="default",
        created_at=_TS,
        updated_at=_TS,
    )


def _fresh() -> tuple[MetadataStore, str]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    store = MetadataStore(path)
    store._conn.execute(  # noqa: SLF001 - test helper
        "INSERT INTO corpus_registry "
        "(corpus_id, tenant_id, name, description, created_at, updated_at) "
        "VALUES (?, ?, 'corpus', '', ?, ?)",
        ("eng", "t1", "2024-01-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00"),
    )
    return store, path


def _components():
    store, _ = _fresh()
    client = QdrantClient(location=":memory:")
    vstore = VectorStore(client)
    vstore.create_collection("eng", dense_size=DENSE_DIM)
    pstore = ParentStore()
    registry = InMemoryCorpusRegistry([_corpus_config()])
    mgr = DocumentManager(
        metadata_store=store,
        vector_store=vstore,
        parent_store=pstore,
        chunker=ParentChildChunker(),
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
        corpus_registry=registry,
    )
    return store, vstore, pstore, registry, mgr


def _ingest(mgr: DocumentManager) -> None:
    acl = ResourceAcl(
        **acl_payload(
            tenant_id="t1",
            acl_scope="restricted",
            security_level="public",
            allowed_user_ids=["u1", "u2"],
        )
    )
    mgr.ingest(
        IngestionRequest(
            tenant_id="t1",
            corpus_id="eng",
            document_id="doc1",
            document_version="v1",
            content=SAMPLE_MARKDOWN,
            acl=acl,
            job_id="j-init",
        )
    )


def _stray_point(vstore: VectorStore, *, document_id: str, version: str, corpus_id: str = "eng"):
    point = PointStruct(
        id=child_point_id(f"stray-{document_id}-{version}"),
        vector={"": [0.0] * DENSE_DIM, "sparse": SparseVector(indices=[0], values=[1.0])},
        payload={
            "tenant_id": "t1",
            "corpus_id": corpus_id,
            "document_id": document_id,
            "document_version": version,
            "text": "stray",
        },
    )
    vstore.upsert(corpus_id, [point])


def test_orphan_qdrant_point_is_purged() -> None:
    store, vstore, pstore, registry, mgr = _components()
    _ingest(mgr)
    _stray_point(vstore, document_id="docX", version="v9")

    rec = Reconciler(store, vstore, pstore, registry, owner="o1")
    report = rec.reconcile_corpus("eng")

    assert any(f.kind == "orphan_qdrant_point" for f in report.findings)
    assert report.mutated is True
    # The stray point is gone; the legit point remains.
    ids = vstore.list_point_ids_by_document("eng", "t1", "eng", "doc1", "v1")
    assert ids  # active doc points untouched
    stray_ids = vstore.list_point_ids_by_document("eng", "t1", "eng", "docX", "v9")
    assert stray_ids == []


def test_missing_data_plane_triggers_rebuild() -> None:
    store, vstore, pstore, registry, mgr = _components()
    _ingest(mgr)
    # Remove the active doc's Qdrant points (simulate data-plane loss).
    lost = vstore.list_point_ids_by_document("eng", "t1", "eng", "doc1", "v1")
    vstore.delete("eng", lost)

    calls: list[tuple] = []
    rec = Reconciler(
        store,
        vstore,
        pstore,
        registry,
        owner="o1",
        rebuild_document=lambda t, c, d, v: (
            calls.append((t, c, d, v)),
            mgr.rebuild_document(t, c, d, v),
        ),
    )
    report = rec.reconcile_corpus("eng")

    assert any(f.kind == "missing_qdrant_point" for f in report.findings)
    assert calls == [("t1", "eng", "doc1", "v1")]
    # Rebuild restored the points.
    assert vstore.list_point_ids_by_document("eng", "t1", "eng", "doc1", "v1")


def test_post_commit_cleanup_retry_purges_lingering_deleted() -> None:
    store, vstore, pstore, registry, mgr = _components()
    _ingest(mgr)
    ctx = make_security_context()
    mgr.delete(ctx, corpus_id="eng", document_id="doc1")  # logical only, not purged

    calls: list[tuple] = []
    rec = Reconciler(
        store,
        vstore,
        pstore,
        registry,
        owner="o1",
        purge_document=lambda t, c, d: calls.append((t, c, d)),
    )
    report = rec.reconcile_corpus("eng")

    assert any(f.kind == "post_commit_cleanup_failure" for f in report.findings)
    assert calls == [("t1", "eng", "doc1")]
    # The reconciler never rolls back the (now-nonexistent) active version.
    assert store.get_active_version("t1", "eng", "doc1") is None


def test_dry_run_reports_without_mutating() -> None:
    store, vstore, pstore, registry, mgr = _components()
    _ingest(mgr)
    _stray_point(vstore, document_id="docX", version="v9")
    lost = vstore.list_point_ids_by_document("eng", "t1", "eng", "doc1", "v1")
    vstore.delete("eng", lost)

    rebuild_calls: list[tuple] = []
    rec = Reconciler(
        store,
        vstore,
        pstore,
        registry,
        owner="o1",
        dry_run=True,
        rebuild_document=lambda t, c, d, v: rebuild_calls.append((t, c, d, v)),
    )
    report = rec.reconcile_corpus("eng")

    assert report.mutated is False
    assert any(f.kind == "orphan_qdrant_point" for f in report.findings)
    assert any(f.kind == "missing_qdrant_point" for f in report.findings)
    assert rebuild_calls == []  # dry-run does not rebuild
    # Nothing actually changed.
    assert vstore.list_point_ids_by_document("eng", "t1", "eng", "docX", "v9")
    assert vstore.list_point_ids_by_document("eng", "t1", "eng", "doc1", "v1") == []


def test_lease_fencing_serializes_per_corpus() -> None:
    store, _ = _fresh()
    assert store.acquire_reconciler_lease("eng", "ownerA", ttl_seconds=300) is True
    # A different owner cannot take the live lease.
    assert store.acquire_reconciler_lease("eng", "ownerB", ttl_seconds=300) is False
    store.release_reconciler_lease("eng", "ownerA")
    assert store.acquire_reconciler_lease("eng", "ownerB", ttl_seconds=300) is True


def test_reconcile_all_iterates_registered_corpora() -> None:
    store, vstore, pstore, registry, mgr = _components()
    _ingest(mgr)
    rec = Reconciler(store, vstore, pstore, registry, owner="o1")
    reports = rec.reconcile_all()
    assert [r.corpus_id for r in reports] == ["eng"]
    assert all(not any(f.kind == "orphan_qdrant_point" for f in r.findings) for r in reports)
