"""E-015 Capability Catalog (build plan §9.1 / Milestone 4).

The catalog declares the capabilities a Corpus may advertise. For the M4
multi-Corpus iteration only ``vector_search`` and ``document_reader`` are
enabled for routing (the existing single-Corpus retrieval + parent-reader
paths). The reserved names ``sql`` / ``api`` / ``graph`` are declared so the
schema is stable, but they are intentionally **not** enabled for M4 — no SQL /
API / graph execution exists yet (deferred to later milestones).

The catalog is fail-closed: an unknown capability is never "supported", and a
capability not in the enabled set is reported as unsupported even if it is a
known reserved name.
"""

from __future__ import annotations

from typing import Literal

# Canonical capability names (build plan §9.1).
Capability = Literal[
    "vector_search",
    "keyword_search",
    "document_reader",
    "sql",
    "api",
    "graph",
]

# Capabilities actually enabled for the M4 multi-Corpus routing iteration.
_ENABLED_CAPABILITIES: frozenset[str] = frozenset({"vector_search", "document_reader"})

# All capability names the catalog knows about (reserved names included). Used
# for validation so an unknown string is rejected rather than silently accepted.
_KNOWN_CAPABILITIES: frozenset[str] = frozenset(
    {
        "vector_search",
        "keyword_search",
        "document_reader",
        "sql",
        "api",
        "graph",
    }
)


class CapabilityCatalog:
    """Read-only catalog of supported Corpus capabilities (build plan §9.1)."""

    # Enabled for the M4 iteration (frozen; extend only via a later milestone).
    enabled: frozenset[str] = _ENABLED_CAPABILITIES
    # All known capability names (reserved names included).
    known: frozenset[str] = _KNOWN_CAPABILITIES

    @classmethod
    def is_known(cls, capability: str) -> bool:
        """Return True if ``capability`` is a catalog-known name (reserved or not)."""
        return capability in cls.known

    @classmethod
    def supports(cls, capability: str) -> bool:
        """Return True iff ``capability`` is enabled for M4 routing.

        Fail-closed: an unknown capability, or a reserved-but-not-enabled
        capability (``sql`` / ``api`` / ``graph``), is reported as unsupported.
        """
        return capability in cls.enabled

    @classmethod
    def supported_for_routing(cls) -> frozenset[str]:
        """Return the frozen set of capabilities enabled for M4 routing."""
        return cls.enabled
