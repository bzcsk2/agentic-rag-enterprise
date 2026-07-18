"""E-015 three Corpus fixtures (build plan §9.4 / Milestone 4).

Reproducible ``CorpusConfig`` objects for the three document-type corpora the M4
multi-Corpus iteration operates over. The ids / tenant / domain / owner /
``capability_ids`` / ``authority_level`` match build plan §9.4 exactly so the
fixtures double as the canonical registry seed and as test data.

All three share ``tenant_id == "local"``; discoverability between them is driven
by ``SecurityContext.allowed_corpus_ids`` (not by tenant separation), so the
"discover only 2 of 3" acceptance scenario is exercised purely via discovery
policy. ``created_at`` / ``updated_at`` use a fixed timestamp so the configs are
deterministic and hash-stable.
"""

from __future__ import annotations

from datetime import datetime

from agentic_rag_enterprise.domain.corpus import CorpusConfig

_FIXED_TS = datetime(2024, 1, 1, 0, 0, 0)

_PRODUCT_DOCS = CorpusConfig(
    corpus_id="product_docs",
    tenant_id="local",
    name="Product Documentation",
    description=(
        "Contains product manuals, release notes, configuration references, "
        "feature descriptions and supported usage procedures. Use for product "
        "behavior, configuration and versioned feature questions. Do not use "
        "for internal incident history or engineering implementation details."
    ),
    domain="product",
    owner="product-team",
    source_type="documents",
    capability_ids=["vector_search", "document_reader"],
    vector_collection="corpus_product_docs",
    parent_store_namespace="corpus_product_docs",
    enabled=True,
    searchable=True,
    authority_level=80,
    security_policy_id="local_internal",
    created_at=_FIXED_TS,
    updated_at=_FIXED_TS,
)

_ENGINEERING_WIKI = CorpusConfig(
    corpus_id="engineering_wiki",
    tenant_id="local",
    name="Engineering Wiki",
    description=(
        "Contains architecture documents, ADRs, API specifications, deployment "
        "runbooks, service ownership and postmortems. Use for implementation, "
        "architecture and operational questions. Do not use for customer-facing "
        "product commitments unless corroborated by product documentation."
    ),
    domain="engineering",
    owner="engineering",
    source_type="wiki",
    capability_ids=["vector_search", "document_reader"],
    vector_collection="corpus_engineering_wiki",
    parent_store_namespace="corpus_engineering_wiki",
    enabled=True,
    searchable=True,
    authority_level=70,
    security_policy_id="engineering_internal",
    created_at=_FIXED_TS,
    updated_at=_FIXED_TS,
)

_TICKETS = CorpusConfig(
    corpus_id="tickets",
    tenant_id="local",
    name="Support and Engineering Tickets",
    description=(
        "Contains issue reports, troubleshooting histories, workarounds and "
        "resolution notes. Use as operational evidence and examples. Ticket "
        "content may be stale or provisional and must not override current "
        "product documentation or approved engineering decisions."
    ),
    domain="support",
    owner="support",
    source_type="tickets",
    capability_ids=["vector_search", "document_reader"],
    vector_collection="corpus_tickets",
    parent_store_namespace="corpus_tickets",
    enabled=True,
    searchable=True,
    authority_level=40,
    security_policy_id="support_internal",
    created_at=_FIXED_TS,
    updated_at=_FIXED_TS,
)


def three_corpus_fixtures() -> list[CorpusConfig]:
    """Return the three reproducible M4 Corpus fixtures (build plan §9.4)."""
    return [_PRODUCT_DOCS, _ENGINEERING_WIKI, _TICKETS]


def fixture_by_id(corpus_id: str) -> CorpusConfig | None:
    """Return the fixture CorpusConfig for ``corpus_id``, or ``None`` if unknown."""
    for cfg in three_corpus_fixtures():
        if cfg.corpus_id == corpus_id:
            return cfg
    return None
