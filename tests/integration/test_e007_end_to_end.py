"""End-to-end E-007 retrieval: chunk -> upsert -> hybrid -> parent 2nd auth.

Validates the full secure flow with the real chunker feeding the real Qdrant
store and parent store, including tenant isolation and corpus discoverability.
"""

from datetime import datetime

from qdrant_client import QdrantClient

from agentic_rag_enterprise.domain.corpus import CorpusConfig
from agentic_rag_enterprise.ingestion.chunker import ParentChildChunker
from agentic_rag_enterprise.retrieval.hybrid import HybridRetriever
from agentic_rag_enterprise.retrieval.parent_reader import ParentReader
from agentic_rag_enterprise.retrieval.retriever import SecureRetriever
from agentic_rag_enterprise.storage.parent_store import ParentStore
from agentic_rag_enterprise.storage.vector_store import VectorStore
from tests.fixtures import (
    DENSE_DIM,
    FakeDenseEncoder,
    FakeSparseEncoder,
    SAMPLE_MARKDOWN,
    acl_payload,
    make_child_point,
    make_parent_chunk,
    make_security_context,
)


def _corpus(corpus_id: str = "eng", tenant_id: str = "t1", **kw) -> CorpusConfig:
    base: dict = dict(
        corpus_id=corpus_id,
        tenant_id=tenant_id,
        name="Eng",
        description="",
        domain="",
        owner="",
        source_type="wiki",
        capability_ids=[],
        enabled=True,
        searchable=True,
        security_policy_id="p",
        default_security_level="internal",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    base.update(kw)
    return CorpusConfig(**base)


def _ingest(corpus_id: str, tenant_id: str, acl: dict) -> tuple[VectorStore, ParentStore, list]:
    chunker = ParentChildChunker()
    parents, children = chunker.chunk_markdown(
        SAMPLE_MARKDOWN, tenant_id=tenant_id, corpus_id=corpus_id, document_id="doc1"
    )

    client = QdrantClient(location=":memory:")
    store = VectorStore(client)
    store.create_collection(corpus_id, dense_size=DENSE_DIM)

    points = [
        make_child_point(
            i + 1,
            child.text,
            tenant_id=tenant_id,
            corpus_id=corpus_id,
            document_id="doc1",
            document_version="v1",
            parent_id=child.parent_id,
            acl=acl,
        )
        for i, child in enumerate(children)
    ]
    store.upsert(corpus_id, points)

    pstore = ParentStore()
    for parent in parents:
        # Rebuild the stored parent with the same ACL the children carry.
        pstore.put(
            make_parent_chunk(
                parent.parent_id,
                parent.text,
                tenant_id=tenant_id,
                corpus_id=corpus_id,
                document_id="doc1",
                document_version="v1",
                acl=acl,
            )
        )
    return store, pstore, children


def test_end_to_end_returns_authorized_parents() -> None:
    acl = acl_payload(tenant_id="t1", acl_scope="tenant", security_level="public")
    store, pstore, children = _ingest("eng", "t1", acl)
    retriever = SecureRetriever(HybridRetriever(store), ParentReader(pstore))

    result = retriever.retrieve(
        make_security_context(),
        "architecture planner security",
        _corpus(),
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
    )
    assert result.hits
    assert result.denied_parent_ids == []
    for hit, parent in result.hits:
        assert parent.parent_id == hit.parent_id
        assert parent.content
        assert parent.document_version == "v1"


def test_tenant_isolation_end_to_end() -> None:
    acl = acl_payload(tenant_id="t1", acl_scope="tenant", security_level="public")
    store, pstore, _ = _ingest("eng", "t1", acl)
    retriever = SecureRetriever(HybridRetriever(store), ParentReader(pstore))

    # A user from a different tenant gets no hits (filter-less retrieval blocked).
    result = retriever.retrieve(
        make_security_context(tenant_id="t2"),
        "anything",
        _corpus(),
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
    )
    assert result.hits == []


def test_corpus_discoverability_end_to_end() -> None:
    acl = acl_payload(tenant_id="t1", acl_scope="tenant", security_level="public")
    store, pstore, _ = _ingest("eng", "t1", acl)
    retriever = SecureRetriever(HybridRetriever(store), ParentReader(pstore))

    ctx = make_security_context(allowed_corpus_ids=["other_corpus"])
    result = retriever.retrieve(
        ctx,
        "anything",
        _corpus(),
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
    )
    assert result.hits == []


def test_disabled_corpus_blocks() -> None:
    acl = acl_payload(tenant_id="t1", acl_scope="tenant", security_level="public")
    store, pstore, _ = _ingest("eng", "t1", acl)
    retriever = SecureRetriever(HybridRetriever(store), ParentReader(pstore))

    result = retriever.retrieve(
        make_security_context(),
        "anything",
        _corpus(enabled=False),
        dense_encoder=FakeDenseEncoder(),
        sparse_encoder=FakeSparseEncoder(),
    )
    assert result.hits == []
