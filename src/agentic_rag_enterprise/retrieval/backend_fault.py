"""E-016 explicit backend-fault boundary (build plan §9.5 / Milestone 4).

The multi-corpus path must only ever capture *infrastructure* faults as a
:class:`~agentic_rag_enterprise.retrieval.multi_corpus.CorpusRetrievalFault`.
Security, authorization, binding and configuration errors, as well as plain
programming bugs (``ValueError`` / ``TypeError`` / ``KeyError`` / ``AssertionError``
from an adapter), must propagate untouched so they can never be relabelled as a
benign partial retrieval.

This module is the *single* place that classifies a per-corpus retrieval failure.
A narrow, curated set of transport / infrastructure exceptions is downgraded to
:class:`RetrievalBackendError`; everything else is re-raised. Adapter code that
knows it is hitting an unreliable dependency may raise :class:`RetrievalBackendError`
directly — but a bare ``except Exception`` elsewhere is forbidden.
"""

from __future__ import annotations

from agentic_rag_enterprise.retrieval.models import RetrievalBackendError

# Infrastructure exception types that are genuinely "the backend is down / slow",
# not a logic or authorization problem. Only these are captured as backend faults.
_BACKEND_EXC_TYPES: tuple[type[Exception], ...] = (ConnectionError, TimeoutError)

try:  # pragma: no cover - import guards for optional qdrant transport errors
    from qdrant_client.http.exceptions import (
        ResponseHandlingException,
        UnexpectedResponse,
    )

    _BACKEND_EXC_TYPES = (*_BACKEND_EXC_TYPES, UnexpectedResponse, ResponseHandlingException)
except Exception:  # pragma: no cover
    pass


def wrap_backend_fault(call):
    """Run ``call`` (a zero-arg callable) and classify the outcome.

    * Re-raises any security / authorization / binding / configuration error as-is.
    * Converts a curated set of infrastructure exceptions into
      :class:`RetrievalBackendError`.
    * Any other exception (including programming bugs) propagates unchanged.

    Returns the call's value on success.
    """
    try:
        return call()
    except RetrievalBackendError:
        raise
    except _BACKEND_EXC_TYPES as exc:
        raise RetrievalBackendError(
            f"retrieval backend failure: {type(exc).__name__}: {exc}"
        ) from exc
