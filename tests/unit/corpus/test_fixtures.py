"""Unit tests for the E-015 three Corpus fixtures (build plan §9.4)."""

from agentic_rag_enterprise.corpus.fixtures import (
    fixture_by_id,
    three_corpus_fixtures,
)


def test_three_fixtures_present() -> None:
    fixtures = three_corpus_fixtures()
    ids = {c.corpus_id for c in fixtures}
    assert ids == {"product_docs", "engineering_wiki", "tickets"}


def test_fixtures_match_build_plan_section_94() -> None:
    by_id = {c.corpus_id: c for c in three_corpus_fixtures()}
    product = by_id["product_docs"]
    assert product.tenant_id == "local"
    assert product.domain == "product"
    assert product.owner == "product-team"
    assert product.capability_ids == ["vector_search", "document_reader"]
    assert product.authority_level == 80
    assert product.vector_collection == "corpus_product_docs"

    eng = by_id["engineering_wiki"]
    assert eng.domain == "engineering"
    assert eng.owner == "engineering"
    assert eng.authority_level == 70
    assert eng.vector_collection == "corpus_engineering_wiki"

    tickets = by_id["tickets"]
    assert tickets.domain == "support"
    assert tickets.owner == "support"
    assert tickets.authority_level == 40
    assert tickets.vector_collection == "corpus_tickets"


def test_all_fixtures_enabled_and_searchable() -> None:
    for c in three_corpus_fixtures():
        assert c.enabled is True
        assert c.searchable is True


def test_fixture_by_id_lookup() -> None:
    assert fixture_by_id("product_docs") is not None
    assert fixture_by_id("does_not_exist") is None
