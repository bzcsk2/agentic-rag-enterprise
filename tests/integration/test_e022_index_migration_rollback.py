"""Integration tests for E-022 index migration + active-version rollback.

Exercises the full build -> switch -> rollback cycle against a real ingest, and
the active-version rollback (build plan §2630) against real version rows. Verifies
the retrieval pointer (CorpusConfig.vector_collection) flips atomically, v1 is
retained (never cleared-and-rebuilt), and a rolled-back version is still
retrievable while the superseded version is deprecated.

Hermetic: in-memory SQLite + in-memory Qdrant + Fake encoders.
"""

import os
import tempfile

from qdrant_client import QdrantClient

from agentic_rag_enterprise.corpus.registry import InMemoryCorpusRegistry
from agentic_rag_enterprise.domain.corpus import CorpusConfig
from agentic_rag_enterprise.ingestion.chunker import ParentChildChunker
from agentic_rag_enterprise.ingestion.index_migration import (
    build_index_v2,
    new_collection_name,
    rollback_index,
    switch_index,
)
from agentic_rag_enterprise.ingestion.job import DocumentManager, IngestionRequest
from agentic_rag_enterprise.security.policy import ResourceAcl
from agentic_rag_enterprise.storage.metadata_store import MetadataStore
from agentic_rag_enterprise.storage.parent_store import ParentStore
from agentic_rag_enterprise.storage.vector_store import VectorStore

from tests.fixtures import (
    DENSE_DIM,
    FakeDenseEncoder,
    FakeSparseEncoder,
    SAMPLE_MARKDOWN,
    acl_payload,
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


def _components():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    store = MetadataStore(path)
    store._conn.execute(  # noqa: SLF001
        "INSERT INTO corpus_registry "
        "(corpus_id, tenant_id, name, description, created_at, updated_at) "
        "VALUES (?, ?, 'corpus', '', ?, ?)",
        ("eng", "t1", "2024-01-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00"),
    )
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
    mgr.ingest(
        IngestionRequest(
            tenant_id="t1",
            corpus_id="eng",
            document_id="doc1",
            document_version="v1",
            content=SAMPLE_MARKDOWN,
            acl=ResourceAcl(
                **acl_payload(tenant_id="t1", acl_scope="restricted", security_level="public")
            ),
            job_id="j-init",
        )
    )
    return store, vstore, pstore, registry, mgr


def test_build_then_switch_keeps_v1_and_retrieval_points_to_v2() -> None:
    store, vstore, pstore, registry, mgr = _components()
    v1_points = vstore.list_point_ids_by_document("eng", "t1", "eng", "doc1", "v1")
    assert v1_points  # sanity: ingest populated the live collection

    v2 = build_index_v2(
        "eng",
        embedding_version="v2",
        chunking_version="v1",
        dense_size=DENSE_DIM,
        metadata_store=store,
        vector_store=vstore,
        corpus_registry=registry,
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
    )
    assert v2 == new_collection_name("eng", embedding_version="v2", chunking_version="v1")
    # v2 built alongside v1; both carry the same points.
    assert vstore.collection_exists(v2)
    assert len(vstore.list_point_ids_by_document(v2, "t1", "eng", "doc1", "v1")) == len(v1_points)
    assert registry.resolve_collection_name("eng") == "eng"  # build != switch

    switch_index(
        "eng",
        target_collection=v2,
        metadata_store=store,
        corpus_registry=registry,
        vector_store=vstore,
    )
    # After switch, retrieval pointer (and persisted registry) both point at v2.
    assert registry.resolve_collection_name("eng") == v2
    assert store.get_active_collection("eng") == v2
    # v2 is now the collection the pointer resolves to; its points are intact.
    assert vstore.list_point_ids_by_document(v2, "t1", "eng", "doc1", "v1") == v1_points
    # v1 is retained, not deleted.
    assert vstore.collection_exists("eng")


def test_rollback_index_restores_v1_and_retains_v2() -> None:
    store, vstore, pstore, registry, mgr = _components()
    v2 = build_index_v2(
        "eng",
        embedding_version="v2",
        chunking_version="v1",
        dense_size=DENSE_DIM,
        metadata_store=store,
        vector_store=vstore,
        corpus_registry=registry,
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
    )
    switch_index(
        "eng",
        target_collection=v2,
        metadata_store=store,
        corpus_registry=registry,
        vector_store=vstore,
    )

    previous = rollback_index(
        "eng", metadata_store=store, corpus_registry=registry, vector_store=vstore
    )
    assert previous == "eng"  # pointer returns to v1
    assert registry.resolve_collection_name("eng") == "eng"
    assert store.get_active_collection("eng") == "eng"
    # v1 retrieval still serves the doc after rollback.
    assert vstore.list_point_ids_by_document("eng", "t1", "eng", "doc1", "v1")
    # v2 is retained (superseded, never cleared-and-rebuilt) for later purge.
    assert vstore.collection_exists(v2)


def test_rollback_active_version_returns_previous_and_deprecates_newer() -> None:
    store, vstore, pstore, registry, mgr = _components()
    # Publish a newer version; v1 becomes deprecated, v2 active.
    mgr.ingest(
        IngestionRequest(
            tenant_id="t1",
            corpus_id="eng",
            document_id="doc1",
            document_version="v2",
            content="# Updated\n\nDifferent body text for v2.",
            acl=ResourceAcl(
                **acl_payload(tenant_id="t1", acl_scope="restricted", security_level="public")
            ),
            job_id="j-v2",
        )
    )
    assert store.get_active_version("t1", "eng", "doc1") == "v2"

    new_rev, prior = mgr.rollback_active_version("t1", "eng", "doc1")
    assert prior == "v2"
    assert isinstance(new_rev, int)
    # v1 is active again; v2 is deprecated (not deleted / not resurrected-from-deleted).
    assert store.get_active_version("t1", "eng", "doc1") == "v1"
    v2_row = store.get_document("t1", "eng", "doc1", "v2")
    assert v2_row is not None and v2_row.status.value == "deprecated"


def test_rollback_active_version_is_idempotent() -> None:
    store, vstore, pstore, registry, mgr = _components()
    mgr.ingest(
        IngestionRequest(
            tenant_id="t1",
            corpus_id="eng",
            document_id="doc1",
            document_version="v2",
            content="# Updated\n\nDifferent body text for v2.",
            acl=ResourceAcl(
                **acl_payload(tenant_id="t1", acl_scope="restricted", security_level="public")
            ),
            job_id="j-v2",
        )
    )
    rev1, _ = mgr.rollback_active_version("t1", "eng", "doc1")
    # Re-asserting the same (already-active) target is a no-op (no revision bump).
    rev2, _ = mgr.rollback_active_version("t1", "eng", "doc1", to_version="v1")
    assert rev2 == rev1
    assert store.get_active_version("t1", "eng", "doc1") == "v1"
