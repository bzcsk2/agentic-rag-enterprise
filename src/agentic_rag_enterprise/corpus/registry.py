"""E-015 Corpus Registry (build plan §9.2 / Milestone 4).

The registry is the single source of truth for "which corpora exist and which a
caller may see". It is the control plane for the M4 multi-Corpus iteration: the
permission-aware soft router (E-016) consumes only what ``list_searchable`` /
``resolve_candidates`` return — the model never sees the full corpus map.

Discoverability is fail-closed and composed of (build plan §9.2 + E-007
contract):

* tenancy (corpus tenant must equal the caller tenant),
* ``SecurityContext.allowed_corpus_ids`` (``None`` = all discoverable, else a
  restrict list),
* ``CorpusConfig.enabled`` and ``CorpusConfig.searchable``.

A non-discoverable Corpus is never returned by ``get`` (raises
``CorpusNotDiscoverableError``) or present in ``list_searchable`` /
``resolve_candidates`` output. Its name, description, capabilities and existence
therefore cannot leak into router input, retrieval requests, Evidence or debug
output.
"""

from __future__ import annotations

from typing import Protocol

from agentic_rag_enterprise.corpus.capability_registry import CapabilityCatalog
from agentic_rag_enterprise.corpus.fixtures import three_corpus_fixtures
from agentic_rag_enterprise.domain.corpus import CorpusConfig
from agentic_rag_enterprise.domain.security import SecurityContext
from agentic_rag_enterprise.retrieval.models import CorpusNotDiscoverableError
from agentic_rag_enterprise.security.policy import can_discover_corpus


class CorpusRegistry(Protocol):
    """Registry surface the router and callers depend on (build plan §9.2)."""

    def get(self, corpus_id: str, security_context: SecurityContext) -> CorpusConfig: ...
    def list_searchable(self, security_context: SecurityContext) -> list[CorpusConfig]: ...
    def resolve_candidates(
        self, query: str, security_context: SecurityContext, limit: int
    ) -> list[CorpusConfig]: ...
    def resolve_collection_name(self, corpus_id: str) -> str: ...
    def set_active_collection(self, corpus_id: str, collection_name: str) -> None: ...
    def list_corpus_ids(self) -> list[str]: ...


def _is_discoverable(corpus: CorpusConfig, ctx: SecurityContext) -> bool:
    """Fail-closed discoverability: tenant + allowed_corpus_ids + enabled + searchable."""
    if corpus.tenant_id != ctx.tenant_id:
        return False
    if not corpus.enabled or not corpus.searchable:
        return False
    return can_discover_corpus(ctx, corpus.corpus_id)


class InMemoryCorpusRegistry:
    """In-memory ``CorpusRegistry`` seeded from the three M4 fixtures (§9.4)."""

    def __init__(self, corpora: list[CorpusConfig] | None = None) -> None:
        self._corpora: dict[str, CorpusConfig] = {
            c.corpus_id: c for c in (corpora if corpora is not None else three_corpus_fixtures())
        }

    def get(self, corpus_id: str, security_context: SecurityContext) -> CorpusConfig:
        corpus = self._corpora.get(corpus_id)
        if corpus is None or not _is_discoverable(corpus, security_context):
            raise CorpusNotDiscoverableError(
                f"corpus {corpus_id!r} is not discoverable for tenant "
                f"{security_context.tenant_id!r}"
            )
        return corpus

    def list_searchable(self, security_context: SecurityContext) -> list[CorpusConfig]:
        return [c for c in self._corpora.values() if _is_discoverable(c, security_context)]

    def resolve_candidates(
        self, query: str, security_context: SecurityContext, limit: int
    ) -> list[CorpusConfig]:
        """Deterministic, capability-aware candidate resolution (registry surface).

        Returns discoverable corpora whose ``capability_ids`` intersect the M4
        enabled capabilities, ordered stably by ``corpus_id`` and truncated to
        ``limit``. The selection / confidence policy (top-1/top-2, ``route_confidence``)
        is the E-016 router's job; this method only narrows to discoverable,
        capability-eligible corpora so the router never receives an unauthorized
        or capability-less candidate.
        """
        enabled = CapabilityCatalog.supported_for_routing()
        candidates = [
            c
            for c in self._corpora.values()
            if _is_discoverable(c, security_context) and set(c.capability_ids) & enabled
        ]
        candidates.sort(key=lambda c: c.corpus_id)
        if limit is not None and limit >= 0:
            candidates = candidates[:limit]
        return candidates

    def resolve_collection_name(self, corpus_id: str) -> str:
        """Control-plane active collection pointer for a corpus (build plan §10.8).

        Returns ``CorpusConfig.vector_collection`` when set, else falls back to
        ``corpus_id``. This is the name the hybrid retriever actually queries
        (``hybrid.py``), so flipping it switches retrieval to a migrated index.
        """
        corpus = self._corpora.get(corpus_id)
        if corpus is None:
            return corpus_id
        return corpus.vector_collection or corpus_id

    def set_active_collection(self, corpus_id: str, collection_name: str) -> None:
        """Flip the live active-collection pointer (index migration switch).

        Updates the in-memory :class:`CorpusConfig` the retriever reads. The
        persisted record is owned by ``MetadataStore.set_active_collection``;
        index migration calls both so the switch survives a restart.
        """
        corpus = self._corpora.get(corpus_id)
        if corpus is None:
            return
        self._corpora[corpus_id] = corpus.model_copy(update={"vector_collection": collection_name})

    def list_corpus_ids(self) -> list[str]:
        return list(self._corpora.keys())
