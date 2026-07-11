"""Baseline characterization for context compression capability.

This capability is NOT YET IMPLEMENTED in the target. The upstream
should_compress_context and compress_context nodes will be ported in a
corresponding capability Issue.

Once ported, this file must be expanded with actual compression tests:
- test_should_compress_triggers_at_token_threshold
- test_compress_preserves_key_facts
- test_compress_tracks_already_retrieved_keys
"""

from agentic_rag_enterprise.graph.runtime import AgenticRagRuntime


def test_runtime_no_context_compression_yet() -> None:
    """Negative characterization: context compression is currently absent.

    The runtime completes without any compression events in the trace.
    Once compression is implemented, at least one trace event should
    reference compression logic; at that point, update or remove this test.
    """
    runtime = AgenticRagRuntime()
    state = runtime.run("What is RAG?")
    assert state.stop_reason == "sufficient_context", (
        "Current runtime stops after first sufficient judgement. "
        "Context compression is not applied."
    )
    assert not any(
        "compress" in t.get("event_type", "").lower()
        or "compress" in str(t.get("payload", {})).lower()
        for t in state.trace
    ), "No trace event should reference compression in the current scaffold."
