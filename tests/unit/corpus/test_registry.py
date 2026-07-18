"""Unit tests for the E-015 CorpusRegistry discoverability (build plan §9.2)."""

from agentic_rag_enterprise.corpus.registry import InMemoryCorpusRegistry
from agentic_rag_enterprise.domain.security import SecurityContext
from agentic_rag_enterprise.retrieval.models import CorpusNotDiscoverableError


def _ctx(tenant_id: str = "local", allowed_corpus_ids: list[str] | None = None) -> SecurityContext:
    return SecurityContext(
        request_id="r",
        session_id="s",
        tenant_id=tenant_id,
        user_id="u",
        policy_version="1.0",
        allowed_corpus_ids=allowed_corpus_ids,
    )


def test_list_searchable_returns_all_when_unrestricted() -> None:
    reg = InMemoryCorpusRegistry()
    visible = reg.list_searchable(_ctx())
    assert {c.corpus_id for c in visible} == {
        "product_docs",
        "engineering_wiki",
        "tickets",
    }


def test_user_discovers_only_two_of_three() -> None:
    # Scenario 1: a caller may discover exactly 2 of the 3 corpora; the third
    # must be completely invisible (never returned, never raised-with-leak).
    reg = InMemoryCorpusRegistry()
    ctx = _ctx(allowed_corpus_ids=["product_docs", "engineering_wiki"])
    visible = reg.list_searchable(ctx)
    assert {c.corpus_id for c in visible} == {"product_docs", "engineering_wiki"}

    # The denied corpus is neither listed nor retrievable.
    assert {c.corpus_id for c in reg.resolve_candidates("anything", ctx, limit=10)} == {
        c.corpus_id for c in visible
    }
    try:
        reg.get("tickets", ctx)
        raise AssertionError("expected CorpusNotDiscoverableError")
    except CorpusNotDiscoverableError:
        pass


def test_get_fails_closed_on_non_discoverable() -> None:
    reg = InMemoryCorpusRegistry()
    ctx = _ctx(allowed_corpus_ids=["product_docs"])
    # Allowed corpus resolves fine.
    assert reg.get("product_docs", ctx).corpus_id == "product_docs"
    # Denied corpus raises (fail-closed), and the error does not reveal the
    # corpus description.
    err = None
    try:
        reg.get("tickets", ctx)
    except CorpusNotDiscoverableError as exc:
        err = exc
    assert err is not None
    assert "tickets" in str(err)
    assert "resolution notes" not in str(err)  # description must not leak


def test_disabled_corpus_excluded_from_discovery() -> None:
    from agentic_rag_enterprise.domain.corpus import CorpusConfig
    from datetime import datetime

    disabled = CorpusConfig(
        corpus_id="secret_corpus",
        tenant_id="local",
        name="Secret",
        description="hidden",
        domain="x",
        owner="x",
        source_type="documents",
        capability_ids=["vector_search"],
        enabled=False,  # disabled
        searchable=True,
        authority_level=90,
        security_policy_id="p",
        created_at=datetime(2024, 1, 1),
        updated_at=datetime(2024, 1, 1),
    )
    reg = InMemoryCorpusRegistry(corpora=[disabled])
    ctx = _ctx(allowed_corpus_ids=["secret_corpus"])
    assert reg.list_searchable(ctx) == []
    try:
        reg.get("secret_corpus", ctx)
        raise AssertionError("expected CorpusNotDiscoverableError for disabled corpus")
    except CorpusNotDiscoverableError:
        pass


def test_resolve_candidates_deterministic_and_capability_filtered() -> None:
    reg = InMemoryCorpusRegistry()
    ctx = _ctx()  # unrestricted, all three capability-eligible
    cands = reg.resolve_candidates("how do I configure X?", ctx, limit=10)
    # Stable order by corpus_id, all three present.
    assert [c.corpus_id for c in cands] == [
        "engineering_wiki",
        "product_docs",
        "tickets",
    ]
    # Limit is honoured.
    limited = reg.resolve_candidates("how do I configure X?", ctx, limit=2)
    assert len(limited) == 2
    assert [c.corpus_id for c in limited] == ["engineering_wiki", "product_docs"]


def test_resolve_candidates_excludes_undiscoverable() -> None:
    reg = InMemoryCorpusRegistry()
    ctx = _ctx(allowed_corpus_ids=["product_docs"])
    cands = reg.resolve_candidates("x", ctx, limit=10)
    assert [c.corpus_id for c in cands] == ["product_docs"]


def test_tenancy_boundary_blocks_other_tenant_corpus() -> None:
    reg = InMemoryCorpusRegistry()
    ctx = _ctx(tenant_id="other-tenant", allowed_corpus_ids=None)
    assert reg.list_searchable(ctx) == []
    try:
        reg.get("product_docs", ctx)
        raise AssertionError("expected CorpusNotDiscoverableError for cross-tenant")
    except CorpusNotDiscoverableError:
        pass
