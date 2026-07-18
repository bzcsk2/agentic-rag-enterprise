"""E-015 Corpus / Capability Registry package (build plan §9 / Milestone 4)."""

from agentic_rag_enterprise.corpus.capability_registry import (
    CapabilityCatalog,
)
from agentic_rag_enterprise.corpus.fixtures import (
    fixture_by_id,
    three_corpus_fixtures,
)
from agentic_rag_enterprise.corpus.registry import (
    CorpusRegistry,
    InMemoryCorpusRegistry,
)

__all__ = [
    "CapabilityCatalog",
    "CorpusRegistry",
    "InMemoryCorpusRegistry",
    "fixture_by_id",
    "three_corpus_fixtures",
]
