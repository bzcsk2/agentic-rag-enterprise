"""Security tests: registry discoverability agrees with `can_discover_corpus` and
never leaks a non-discoverable Corpus identity (build plan §9.2 / E-015)."""

from agentic_rag_enterprise.corpus.registry import InMemoryCorpusRegistry
from agentic_rag_enterprise.domain.security import SecurityContext
from agentic_rag_enterprise.retrieval.models import CorpusNotDiscoverableError
from agentic_rag_enterprise.security.policy import can_discover_corpus


def _ctx(allowed_corpus_ids: list[str] | None) -> SecurityContext:
    return SecurityContext(
        request_id="r",
        session_id="s",
        tenant_id="local",
        user_id="u",
        policy_version="1.0",
        allowed_corpus_ids=allowed_corpus_ids,
    )


def test_registry_and_policy_agree_on_discoverability() -> None:
    reg = InMemoryCorpusRegistry()
    allowed = ["product_docs", "engineering_wiki"]
    ctx = _ctx(allowed_corpus_ids=allowed)
    for corpus_id in ("product_docs", "engineering_wiki", "tickets"):
        listed = any(c.corpus_id == corpus_id for c in reg.list_searchable(ctx))
        assert listed == can_discover_corpus(ctx, corpus_id)


def test_third_corpus_never_leaks() -> None:
    reg = InMemoryCorpusRegistry()
    ctx = _ctx(allowed_corpus_ids=["product_docs", "engineering_wiki"])
    # The denied corpus must not appear in any returned config (name/description/
    # capability/existence all hidden).
    for cfg in reg.list_searchable(ctx):
        assert cfg.corpus_id != "tickets"
    for cfg in reg.resolve_candidates("compare product and tickets", ctx, limit=10):
        assert cfg.corpus_id != "tickets"
    # And `get` fails closed without revealing the description.
    try:
        reg.get("tickets", ctx)
        raise AssertionError("expected CorpusNotDiscoverableError")
    except CorpusNotDiscoverableError as exc:
        assert "resolution notes" not in str(exc)
