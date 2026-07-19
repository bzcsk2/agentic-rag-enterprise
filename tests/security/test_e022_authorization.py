"""Security tests for E-022 reconciler + active-version rollback.

Focus: the automated control-plane operations must never leak or resurrect
evidence (build plan §10.10 + E-022 contract §8 #9):

* The reconciler's physical-purge callback is driven ONLY by the Metadata DB
  truth set — it is never called for an ``active`` document, so a clean corpus
  is never purged. It is only authorized to finish a post-commit cleanup for a
  document the control plane has already logically marked ``deleted``.
* ``rollback_active_version`` refuses to reactivate a ``deleted`` (purged)
  version and is CAS-guarded so a stale attempt cannot overwrite a newer
  committed revision or operate across tenant/corpus boundaries.

All hermetic (in-memory SQLite + in-memory Qdrant + Fake encoders). The
reconciler/rollback are control-plane processes and take no user
``SecurityContext``; their safety comes from the Metadata DB authority, not from
a per-request ACL check.
"""

import os
import tempfile

from qdrant_client import QdrantClient

from agentic_rag_enterprise.corpus.registry import InMemoryCorpusRegistry
from agentic_rag_enterprise.domain.corpus import CorpusConfig
from agentic_rag_enterprise.domain.ingestion import DocumentStatus
from agentic_rag_enterprise.ingestion.chunker import ParentChildChunker
from agentic_rag_enterprise.ingestion.job import DocumentManager, IngestionRequest
from agentic_rag_enterprise.ingestion.reconciler import Reconciler
from agentic_rag_enterprise.security.policy import ResourceAcl
from agentic_rag_enterprise.storage.metadata_store import MetadataStore, ActiveVersionConflict
from agentic_rag_enterprise.storage.parent_store import ParentStore
from agentic_rag_enterprise.storage.vector_store import VectorStore

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
    return store, vstore, pstore, registry, mgr


def _ingest(mgr: DocumentManager, *, document_id: str = "doc1", version: str = "v1") -> None:
    mgr.ingest(
        IngestionRequest(
            tenant_id="t1",
            corpus_id="eng",
            document_id=document_id,
            document_version=version,
            content=SAMPLE_MARKDOWN,
            acl=ResourceAcl(
                **acl_payload(
                    tenant_id="t1",
                    acl_scope="restricted",
                    security_level="public",
                    allowed_user_ids=["u1", "u2"],
                )
            ),
            job_id=f"j-{document_id}-{version}",
        )
    )


def test_reconciler_never_purges_an_active_document() -> None:
    """A healthy active document must survive reconciliation untouched.

    The purge callback is only invoked for documents the Metadata DB marks
    ``deleted``; an active document is never a cleanup target, so a clean corpus
    is never physically purged by the reconciler.
    """
    store, vstore, pstore, registry, mgr = _components()
    _ingest(mgr)
    points_before = vstore.list_point_ids_by_document("eng", "t1", "eng", "doc1", "v1")

    rec = Reconciler(
        store,
        vstore,
        pstore,
        registry,
        owner="o1",
        purge_document=mgr.reconcile_purge,
        rebuild_document=mgr.rebuild_document,
    )
    report = rec.reconcile_corpus("eng")

    # No post-commit-cleanup finding for a live, active document.
    assert not any(f.kind == "post_commit_cleanup_failure" for f in report.findings)
    # Active version + data plane preserved.
    assert store.get_active_version("t1", "eng", "doc1") == "v1"
    assert vstore.list_point_ids_by_document("eng", "t1", "eng", "doc1", "v1") == points_before
    # Metadata row still present (never purged).
    assert store.get_document_latest("t1", "eng", "doc1") is not None


def test_reconcile_purge_only_finishes_logically_deleted_document() -> None:
    """Physical purge via reconciler is gated by the logical-delete truth.

    After a control-plane logical delete (Metadata DB status=deleted), the
    lingering data plane is purged; the metadata row is then removed. Before a
    logical delete the reconciler does nothing to that document.
    """
    store, vstore, pstore, registry, mgr = _components()
    _ingest(mgr)
    ctx = make_security_context()
    mgr.delete(ctx, corpus_id="eng", document_id="doc1")  # logical delete only
    # Data plane still lingers (post-commit cleanup not yet run).
    assert vstore.list_point_ids_by_document("eng", "t1", "eng", "doc1", "v1")

    rec = Reconciler(
        store,
        vstore,
        pstore,
        registry,
        owner="o1",
        purge_document=mgr.reconcile_purge,
        rebuild_document=mgr.rebuild_document,
    )
    report = rec.reconcile_corpus("eng")

    assert any(f.kind == "post_commit_cleanup_failure" for f in report.findings)
    # Everything for doc1 is gone: data plane + metadata row.
    assert vstore.list_point_ids_by_document("eng", "t1", "eng", "doc1", "v1") == []
    assert store.get_document_latest("t1", "eng", "doc1") is None


def test_rollback_refuses_to_reactivate_a_deleted_version() -> None:
    """A purged (``deleted``) version can never be resurrected by rollback."""
    store, vstore, pstore, registry, mgr = _components()
    _ingest(mgr, document_id="doc1", version="v1")
    _ingest(mgr, document_id="doc1", version="v2")  # v1 deprecated, v2 active
    # Mark the candidate v1 as purged (deleted) evidence directly. (logical_delete
    # always removes *active* visibility by design, so we flip v1's status here.)
    store.set_document_status("t1", "eng", "doc1", "v1", DocumentStatus.DELETED, deleted_at=_TS)

    try:
        mgr.rollback_active_version("t1", "eng", "doc1", to_version="v1")
        raise AssertionError("expected ActiveVersionConflict")
    except ActiveVersionConflict:
        pass
    # Active version is unchanged; the deleted version stays deleted.
    assert store.get_active_version("t1", "eng", "doc1") == "v2"
    assert store.get_document("t1", "eng", "doc1", "v1").status.value == "deleted"


def test_rollback_active_version_cas_guards_stale_revision() -> None:
    """A stale expected_revision loses the CAS and protects the newer revision."""
    store, vstore, pstore, registry, mgr = _components()
    _ingest(mgr, document_id="doc1", version="v1")
    _ingest(mgr, document_id="doc1", version="v2")  # revision bumped
    # Capture the revision as it stands after v2 (now stale once v3 lands).
    stale_rev = store.get_current_revision("t1", "eng", "doc1")
    _ingest(mgr, document_id="doc1", version="v3")  # bumps revision again

    try:
        mgr.rollback_active_version(
            "t1", "eng", "doc1", to_version="v2", expected_revision=stale_rev
        )
        raise AssertionError("expected ActiveVersionConflict on stale revision")
    except ActiveVersionConflict:
        pass
    # The newer active version (v3) is preserved; no resurrection to v2.
    assert store.get_active_version("t1", "eng", "doc1") == "v3"


def test_rollback_is_tenant_scoped() -> None:
    """Rollback cannot act across tenant boundaries (no cross-tenant resurrection)."""
    store, vstore, pstore, registry, mgr = _components()
    _ingest(mgr, document_id="doc1", version="v1")
    _ingest(mgr, document_id="doc1", version="v2")

    # A request for a different tenant finds no active version to roll back.
    try:
        mgr.rollback_active_version("other-tenant", "eng", "doc1")
        raise AssertionError("expected ActiveVersionConflict for foreign tenant")
    except ActiveVersionConflict:
        pass
    # t1's active version is untouched.
    assert store.get_active_version("t1", "eng", "doc1") == "v2"
