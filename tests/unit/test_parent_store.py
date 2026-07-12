"""Unit tests for ParentStore bulk document helpers (E-010).

P1-2: the bulk helpers MUST be scoped by ``tenant_id`` + ``corpus_id``, not just
``document_id`` + ``document_version`` — a shared parent store must never
cross-tenant / cross-corpus mutate (build plan §10.6/§10.7).
"""

from agentic_rag_enterprise.storage.parent_store import ParentStore

from tests.fixtures import acl_payload, make_parent_chunk


def _store() -> ParentStore:
    s = ParentStore()
    # Target resource: (t1, eng, d1, v1)
    s.put(make_parent_chunk("p1", "x", tenant_id="t1", corpus_id="eng", document_id="d1", document_version="v1", acl=acl_payload()))
    s.put(make_parent_chunk("p2", "y", tenant_id="t1", corpus_id="eng", document_id="d1", document_version="v1", acl=acl_payload()))
    # Same document_id + version but a DIFFERENT tenant.
    s.put(make_parent_chunk("q1", "x", tenant_id="t2", corpus_id="eng", document_id="d1", document_version="v1", acl=acl_payload()))
    # Same document_id + version but a DIFFERENT corpus.
    s.put(make_parent_chunk("r1", "x", tenant_id="t1", corpus_id="fra", document_id="d1", document_version="v1", acl=acl_payload()))
    # A different document in the same tenant/corpus.
    s.put(make_parent_chunk("p3", "z", tenant_id="t1", corpus_id="eng", document_id="d2", document_version="v1", acl=acl_payload()))
    return s


def test_deprecate_document_scoped_to_tenant_corpus() -> None:
    s = _store()
    s.deprecate_document("t1", "eng", "d1", "v1")
    assert s.get("p1").metadata["status"] == "inactive"
    assert s.get("p2").metadata["deprecated"] is True
    # Same id/version in another tenant or corpus is NOT touched.
    assert s.get("q1").metadata["deprecated"] is False
    assert s.get("r1").metadata["deprecated"] is False
    # Other documents untouched.
    assert s.get("p3").metadata["deprecated"] is False


def test_delete_document_scoped_to_tenant_corpus() -> None:
    s = _store()
    s.delete_document("t1", "eng", "d1", "v1")
    assert "p1" not in s and "p2" not in s
    # Same id/version in another tenant or corpus survives.
    assert "q1" in s and "r1" in s
    assert "p3" in s


def test_update_acl_document_scoped_to_tenant_corpus() -> None:
    s = _store()
    s.update_acl_document("t1", "eng", "d1", "v1", {"acl_scope": "restricted", "allowed_user_ids": ["u9"]})
    assert s.get("p1").metadata["acl_scope"] == "restricted"
    assert s.get("p1").metadata["allowed_user_ids"] == ["u9"]
    # Same id/version in another tenant or corpus is NOT patched.
    assert s.get("q1").metadata["acl_scope"] == "tenant"
    assert s.get("r1").metadata["acl_scope"] == "tenant"
    # Other documents untouched.
    assert s.get("p3").metadata["acl_scope"] == "tenant"
