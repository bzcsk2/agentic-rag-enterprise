"""Unit tests for the E-015 CapabilityCatalog (build plan §9.1)."""

from agentic_rag_enterprise.corpus.capability_registry import CapabilityCatalog


def test_enabled_capabilities_match_m4_scope() -> None:
    assert CapabilityCatalog.supported_for_routing() == frozenset(
        {"vector_search", "document_reader"}
    )


def test_enabled_capabilities_supported() -> None:
    assert CapabilityCatalog.supports("vector_search") is True
    assert CapabilityCatalog.supports("document_reader") is True


def test_reserved_capabilities_not_enabled() -> None:
    # sql / api / graph are reserved names but NOT enabled for M4 routing.
    assert CapabilityCatalog.is_known("sql") is True
    assert CapabilityCatalog.is_known("api") is True
    assert CapabilityCatalog.is_known("graph") is True
    assert CapabilityCatalog.supports("sql") is False
    assert CapabilityCatalog.supports("api") is False
    assert CapabilityCatalog.supports("graph") is False


def test_unknown_capability_unsupported() -> None:
    assert CapabilityCatalog.is_known("llm_oracle") is False
    assert CapabilityCatalog.supports("llm_oracle") is False
