# Upstream Capability Map — E-001

## Source Information
| Field | Value |
|---|---|
| Upstream repo | `/vol4/Agent/agentic-rag-for-dummies` |
| Upstream remote | `https://github.com/GiovanniPasq/agentic-rag-for-dummies.git` |
| Upstream commit | `8b3e5ff0619f7ede593d728e4a8b459fbbec9b08` |
| Upstream tag | `v2.3` |
| Upstream license | MIT License — Copyright (c) 2025 Giovanni Pasqualino (`./LICENSE`) |
| Target commit | `6e80b31614d127c4f004e60edcf4d3935653bd2a` |
| Target package | `src/agentic_rag_enterprise/` |
| Inventory date | 2026-07-11 |

## Legend
| Status | Meaning |
|---|---|
| `implemented` | Real implementation with runtime behavior |
| `scaffold` | Interface exists but mock/placeholder only |
| `missing` | No equivalent in target |
| `not-applicable` | Not relevant to enterprise target |

| Strategy | Meaning |
|---|---|
| `port` | Copy upstream core logic with minimal adaptation |
| `wrap` | Adapt upstream via adapter/compatibility layer |
| `compatible-reimplementation` | Rewrite preserving upstream contract |
| `retain-target` | Keep existing target implementation as-is |
| `not-applicable` | No migration required |

---

## Section 1.5 — Baseline Capabilities

### 1. PDF / Markdown Document Ingestion

| Field | Value |
|---|---|
| Upstream file | `project/utils.py`, `project/document_chunker.py` |
| Upstream symbols | `pdf_to_markdown()`, `pdfs_to_markdowns()`, `DocumentChunker.__init__()` |
| Target file | `src/agentic_rag_enterprise/ingestion/chunker.py` |
| Target symbols | `SimpleChunker.chunk()` |
| Status | `scaffold` |
| Strategy | `port` |
| Test plan | Characterization: output shape; Integration: PDF→Markdown→chunk roundtrip |
| Notes | Upstream uses `pymupdf4llm` for PDF→MD and `MarkdownHeaderTextSplitter` for parent-child chunking. Target `SimpleChunker` does character-only split, no PDF conversion, no parent-child hierarchy. Full gap. |

### 2. Markdown Heading-Aware Parent-Child Chunking

| Field | Value |
|---|---|
| Upstream file | `project/document_chunker.py` |
| Upstream symbols | `DocumentChunker` (full class), `__merge_small_parents()`, `__split_large_parents()`, `__clean_small_chunks()`, `__create_child_chunks()` |
| Target file | `src/agentic_rag_enterprise/ingestion/chunker.py` |
| Target symbols | `SimpleChunker.chunk()` (flat character split only) |
| Status | `scaffold` — only flat chunking, no header awareness |
| Strategy | `port` |
| Test plan | Characterization: parent/child count, size ranges, metadata propagation |
| Notes | Upstream `MarkdownHeaderTextSplitter` on `H1`/`H2`/`H3` + `RecursiveCharacterTextSplitter` for children. All rebalancing/merging logic must be ported. |

### 3. Child Chunk Precise Retrieval + Parent Chunk Context Reading

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/tools.py:12`, `project/rag_agent/tools.py:51` |
| Upstream symbols | `ToolFactory._search_child_chunks()`, `ToolFactory._retrieve_parent_chunks()` |
| Target file | `src/agentic_rag_enterprise/retrieval/retriever.py` |
| Target symbols | `Retriever.retrieve()` |
| Status | `scaffold` — mock returns single static evidence |
| Strategy | `port` |
| Test plan | Characterization: tool output format, error cases (no results, missing parent) |
| Notes | Upstream retrieves from Qdrant vector store + JSON parent store. Target has neither. |

### 4. Qdrant Dense + Sparse Hybrid Retrieval

| Field | Value |
|---|---|
| Upstream file | `project/db/vector_db_manager.py` |
| Upstream symbols | `VectorDbManager` (full class), `create_collection()`, `get_collection()` (returns `QdrantVectorStore` with `RetrievalMode.HYBRID`) |
| Target file | — |
| Target symbols | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: collection creation, hybrid search result format |
| Notes | Target `Settings` has `qdrant_url`/`qdrant_api_key` fields but no vector DB manager. Upstream uses local Qdrant path + `HuggingFaceEmbeddings` + `FastEmbedSparse`. |

### 5. Conversation Summary + Bounded Window Memory

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/nodes.py:77` |
| Upstream symbols | `summarize_history()`, `_recent_conversation()`, `_remove_messages_not_in()`, `State.conversation_summary` |
| Target file | — |
| Target symbols | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: summary keeps key facts, bounded retention, removal logic |
| Notes | Upstream uses LLM-powered rolling summary + bounded window. Entirely absent from target. |

### 6. Query Rewriting

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/nodes.py:110`, `project/rag_agent/prompts.py:21` |
| Upstream symbols | `rewrite_query()`, `get_rewrite_query_prompt()`, `QueryAnalysis` schema |
| Target file | — |
| Target symbols | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: query transformation, clarification triggering |
| Notes | Upstream uses structured output LLM call with `QueryAnalysis` Pydantic schema. |

### 7. Query Clarification / Human-in-the-Loop Pause

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/nodes.py:169`, `project/rag_agent/graph.py` |
| Upstream symbols | `request_clarification()`, `interrupt_before=["request_clarification"]` |
| Target file | — |
| Target symbols | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: interrupt triggers, resume flow, clarification surfaces |
| Notes | Upstream uses LangGraph `interrupt_before` on the `request_clarification` node. Entirely absent. |

### 8. Multiple Question Parallel Agent Execution

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/edges.py:7`, `project/rag_agent/graph.py:34` |
| Upstream symbols | `route_after_rewrite()` (returns `list[Send]`), `AgentState` subgraph |
| Target file | — |
| Target symbols | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: parallel Send dispatch, per-question agent state isolation |
| Notes | Upstream uses `langgraph.types.Send` to fan out per-question agents. |

### 9. Tool Calling (ToolNode)

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/graph.py:8`, `project/rag_agent/tools.py` |
| Upstream symbols | `ToolNode` (from `langgraph.prebuilt`), `ToolFactory.create_tools()` |
| Target file | — |
| Target symbols | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: tool dispatch, result routing, budget enforcement |
| Notes | Upstream uses `ToolNode` with `search_child_chunks` and `retrieve_parent_chunks` tools. |

### 10. Self-Correcting Retrieval Loop

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/nodes.py:173` (orchestrator), `project/rag_agent/edges.py:18` (routing) |
| Upstream symbols | `orchestrator()`, `route_after_orchestrator_call()`, `should_compress_context()` |
| Target file | `src/agentic_rag_enterprise/graph/runtime.py` |
| Target symbols | `AgenticRagRuntime.run()` (bounded while-loop with iteration counter) |
| Status | `scaffold` — iteration loop exists but no real tool calls or routing |
| Strategy | `compatible-reimplementation` |
| Test plan | Characterization: loop termination, iteration limits |
| Notes | Target has a sequential loop that does not use LangGraph. Upstream uses full LangGraph state machine with conditional edges and ToolNode. |

### 11. Context Compression

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/nodes.py:259`, `project/rag_agent/prompts.py:105` |
| Upstream symbols | `compress_context()`, `should_compress_context()`, `get_context_compression_prompt()` |
| Target file | — |
| Target symbols | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: token threshold trigger, summary structure, retrieval_keys tracking |
| Notes | Upstream uses token-based threshold + LLM compression with already-retrieved tracking. |

### 12. Tool Call Limit, Iteration Limit, Graph Recursion Limit

| Field | Value |
|---|---|
| Upstream file | `project/config.py` |
| Upstream symbols | `MAX_TOOL_CALLS=8`, `MAX_ITERATIONS=10`, `GRAPH_RECURSION_LIMIT=50` |
| Target file | `src/agentic_rag_enterprise/config.py` |
| Target symbols | `Settings.max_tool_calls=12`, `Settings.max_iterations=3` |
| Status | `scaffold` — config keys exist but no runtime enforcement against LangGraph |
| Strategy | `compatible-reimplementation` |
| Test plan | Characterization: budget exceeded → fallback, graph recursion hit |
| Notes | Target defaults differ (12 vs 8 for tool calls; 3 vs 10 for iterations). `GRAPH_RECURSION_LIMIT` missing. |

### 13. Fallback Answer

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/nodes.py:192`, `project/rag_agent/prompts.py:80` |
| Upstream symbols | `fallback_response()`, `get_fallback_response_prompt()` |
| Target file | `src/agentic_rag_enterprise/agents/synthesis.py` |
| Target symbols | `SynthesisAgent.synthesize()` (handles insufficient evidence → abstain) |
| Status | `scaffold` — abstention case exists but no synthesis from retrieved data |
| Strategy | `compatible-reimplementation` |
| Test plan | Characterization: fallback triggers on timeout/limit, abstention format |
| Notes | Target has abstention but no actual answer-from-evidence synthesis. |

### 14. Multiple Answer Aggregation

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/nodes.py:313`, `project/rag_agent/prompts.py:131` |
| Upstream symbols | `aggregate_answers()`, `get_aggregation_prompt()` |
| Target file | — |
| Target symbols | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: multi-answer merge, conflict handling |
| Notes | Upstream aggregates per-agent answers via LLM after parallel execution. |

### 15. Langfuse Observability

| Field | Value |
|---|---|
| Upstream file | `project/core/observability.py`, `project/config.py` |
| Upstream symbols | `Observability` class, `LANGFUSE_*` config keys |
| Target file | `src/agentic_rag_enterprise/observability/trace.py` |
| Target symbols | `TraceRecorder` (in-memory append-only, no Langfuse integration) |
| Status | `scaffold` — basic trace recorder but no Langfuse SDK integration |
| Strategy | `wrap` — keep TraceRecorder pattern, add Langfuse callback adapter |
| Test plan | Characterization: event recording format; Integration: Langfuse trace shape |
| Notes | Upstream uses `langfuse.langchain.CallbackHandler`. Target has no Langfuse dependency. |

### 16. Gradio Local Interactive UI

| Field | Value |
|---|---|
| Upstream file | `project/ui/gradio_app.py`, `project/ui/css.py`, `project/app.py` |
| Upstream symbols | `create_gradio_ui()`, `custom_css`, `_SuppressOtelDetachWarning` |
| Target file | — |
| Target symbols | — |
| Status | `missing` |
| Strategy | `compatible-reimplementation` |
| Test plan | Characterization: UI renders, tabs switch, file upload flow |
| Notes | Target has FastAPI only (`api/main.py`). Gradio UI entirely absent. |

### 17. RAGAS / Retrieval Evaluation

| Field | Value |
|---|---|
| Upstream file | `requirements.txt` (`ragas==0.4.3`), `notebooks/evaluation.ipynb` (full pipeline) |
| Upstream symbols | `AnswerAccuracy`, `ContextRelevance`, `ResponseGroundedness`, `ContextPrecision`, `ContextRecall` (via NVIDIA metrics) |
| Target file | `src/agentic_rag_enterprise/evals/metrics.py` |
| Target symbols | `EvalResult`, `citation_coverage()` |
| Status | `scaffold` — single eval metric exists (citation coverage) |
| Strategy | `port` — adopt RAGAS metric structure from upstream notebook |
| Test plan | Characterization: metric calculation with/without citations; Integration: RAGAS metric pipeline local run |
| Notes | Upstream has full RAGAS 0.4.3 pipeline with 5 NVIDIA metrics, 30 curated single-hop QA records (`notebooks/data/curated_ragas_qa.json`), CSV evaluation cache, and separate answer/judge models. Requires local Ollama for both answer generation and RAGAS scoring. Target has only a single `citation_coverage` function with no dataset, runner, or judge. Gap is significant. |

---

## Section 3.3 — Must-Retain Execution Logic Symbols

### `summarize_history`

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/nodes.py:77` |
| Target file | — |
| Target symbol | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: summary keeps key facts, bounded retention, removal logic |
| Notes | LangGraph node that maintains a rolling LLM-generated conversation summary. |

### `rewrite_query`

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/nodes.py:110` |
| Target file | — |
| Target symbol | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: query transforms, clarification triggers, structured output schema |
| Notes | Uses structured output LLM call with `QueryAnalysis` schema. |

### `request_clarification`

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/nodes.py:169` |
| Target file | — |
| Target symbol | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: interrupt triggers, resume flow, clarification surfaces |
| Notes | Empty return node; interrupt is handled in graph configuration. |

### `orchestrator`

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/nodes.py:173` |
| Target file | — |
| Target symbol | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: tool call dispatch, LLM+tool interaction, message naming |
| Notes | Core agent node that calls LLM with tool binding. |

### `should_compress_context`

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/nodes.py:222` |
| Target file | — |
| Target symbol | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: token threshold boundary, `Command` goto routing |
| Notes | Conditional edge node that returns `Command` with `goto`. |

### `compress_context`

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/nodes.py:259` |
| Target file | — |
| Target symbol | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: summary structure, retrieval_keys tracking, `RemoveMessage` |
| Notes | LLM-based context compression with retrieval dedup tracking. |

### `fallback_response`

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/nodes.py:192` |
| Target file | `src/agentic_rag_enterprise/agents/synthesis.py` |
| Target symbol | `SynthesisAgent.synthesize()` (abstention path only) |
| Status | `scaffold` |
| Strategy | `compatible-reimplementation` |
| Test plan | Characterization: fallback triggers on timeout/limit; abstention vs synthesis-from-partial |
| Notes | Target handles the "insufficient → abstain" path but not "timeout → synthesize from partial data". |

### `collect_answer`

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/nodes.py:298` |
| Target file | — |
| Target symbol | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: answer extraction from last AIMessage, `agent_answers` packaging |
| Notes | Extracts final answer from last AIMessage, packages `agent_answers`. |

### `aggregate_answers`

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/nodes.py:313` |
| Target file | — |
| Target symbol | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: multi-answer merge, conflict handling, history cleanup |
| Notes | Aggregates parallel agent answers via LLM synthesis. |

### `search_child_chunks`

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/tools.py:12` |
| Target file | — |
| Target symbol | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: result format, score threshold, no-results case, error case |
| Notes | Qdrant similarity search with score threshold, formatted output. |

### `retrieve_parent_chunks`

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/tools.py:51` |
| Target file | — |
| Target symbol | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: JSON store lookup, content+metadata format, missing parent |
| Notes | JSON parent store lookup, formatted output with content + metadata. |

### `ToolNode`

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/graph.py:8` (from `langgraph.prebuilt`) |
| Target file | — |
| Target symbol | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: tool dispatch, result routing, budget enforcement |
| Notes | LangGraph prebuilt ToolNode for executing tool calls. |

### `InMemorySaver` (baseline checkpointer)

| Field | Value |
|---|---|
| Upstream file | `project/rag_agent/graph.py:10` (from `langgraph.checkpoint.memory`) |
| Target file | — |
| Target symbol | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: thread CRUD, state persistence, thread_id isolation |
| Notes | Target uses no LangGraph checkpointer; `AgenticRagRuntime` is a plain Python loop. |

### `MAX_TOOL_CALLS`

| Field | Value |
|---|---|
| Upstream file | `project/config.py` |
| Upstream value | `8` |
| Target file | `src/agentic_rag_enterprise/config.py` |
| Target symbol | `Settings.max_tool_calls=12` |
| Status | `scaffold` — key exists with different default |
| Strategy | `compatible-reimplementation` |
| Test plan | Characterization: budget exceeded → fallback route; boundary at limit+1 |
| Notes | Semantic conflict: upstream limit is 8, target is 12. Must reconcile during port. |

### `MAX_ITERATIONS`

| Field | Value |
|---|---|
| Upstream file | `project/config.py` |
| Upstream value | `10` |
| Target file | `src/agentic_rag_enterprise/config.py` |
| Target symbol | `Settings.max_iterations=3` |
| Status | `scaffold` — key exists with different default |
| Strategy | `compatible-reimplementation` |
| Test plan | Characterization: iteration counter reaches limit → fallback |
| Notes | Upstream counts per-agent iterations; target counts main loop iterations. Semantics differ. |

### `GRAPH_RECURSION_LIMIT`

| Field | Value |
|---|---|
| Upstream file | `project/config.py` |
| Upstream value | `50` |
| Target file | — |
| Target symbol | — |
| Status | `missing` |
| Strategy | `port` |
| Test plan | Characterization: LangGraph recursion error is raised at configured limit |
| Notes | Hard LangGraph recursion limit. Entirely absent from target. |

---

## Target-Specific Capabilities (Not in upstream)

### `AgenticRagState` (typed enterprise state)

| Field | Value |
|---|---|
| Target file | `src/agentic_rag_enterprise/graph/state.py` |
| Status | `scaffold` — full model skeleton, not wired into LangGraph |
| Strategy | `retain-target` |
| Notes | Upstream uses flat `State(MessagesState)` and `AgentState(MessagesState)`. Target has richer schema but no LangGraph integration. |

### `CorpusRegistry`

| Field | Value |
|---|---|
| Target file | `src/agentic_rag_enterprise/retrieval/corpus_registry.py` |
| Status | `scaffold` — in-memory, YAML-loadable, no real routing |
| Strategy | `retain-target` |
| Notes | Enterprise-only concept. Upstream has no corpus concept. |

### `AccessPolicy` (retrieval-time ACL)

| Field | Value |
|---|---|
| Target file | `src/agentic_rag_enterprise/security/policy.py` |
| Status | `scaffold` — basic user-in-allowed-users check only |
| Strategy | `retain-target` |
| Notes | Enterprise-only concept. Upstream has no security model. |

### `FastAPI` entry point

| Field | Value |
|---|---|
| Target file | `src/agentic_rag_enterprise/api/main.py` |
| Status | `scaffold` — `/health` and `/chat` endpoints work with mock data |
| Strategy | `retain-target` |
| Notes | Upstream has Gradio only. Target adds FastAPI as primary API. |

### `PlannerAgent` / `SufficientContextAgent` / `SynthesisAgent`

| Field | Value |
|---|---|
| Target files | `src/agentic_rag_enterprise/agents/planner.py`, `sufficient_context.py`, `synthesis.py` |
| Status | `scaffold` — deterministic mock implementations |
| Strategy | `retain-target` (scaffold interfaces, fill with upstream patterns) |
| Notes | Enterprise agents have no upstream equivalent. Interfaces are placeholders. |

---

## Configuration Key Mapping

| Upstream key | Target key | Status |
|---|---|---|
| `MARKDOWN_DIR` | — | `missing` |
| `PARENT_STORE_PATH` | — | `missing` |
| `QDRANT_DB_PATH` | — | `missing` |
| `CHILD_COLLECTION` | — | `missing` |
| `SPARSE_VECTOR_NAME` | — | `missing` |
| `DENSE_MODEL` | — | `missing` |
| `SPARSE_MODEL` | — | `missing` |
| `LLM_MODEL` | `llm_provider` | `incompatible` — upstream uses model name, target uses provider name |
| `JUDGE_MODEL` | — | `missing` |
| `LLM_TEMPERATURE` | — | `missing` |
| `LLM_SEED` | — | `missing` |
| `RETRIEVAL_SCORE_THRESHOLD` | — | `missing` |
| `DEFAULT_RETRIEVAL_K` | `max_retrieval_top_k` | `scaffold` — same concept, different default (7 vs 8) |
| `CHILD_CHUNK_SEPARATOR` | — | `missing` |
| `MAX_TOOL_CALLS` | `max_tool_calls` | `scaffold` — different default (8 vs 12) |
| `MAX_ITERATIONS` | `max_iterations` | `scaffold` — different semantics (10 vs 3) |
| `GRAPH_RECURSION_LIMIT` | — | `missing` |
| `MAIN_HISTORY_MESSAGES_TO_KEEP` | — | `missing` |
| `BASE_TOKEN_THRESHOLD` | — | `missing` |
| `TOKEN_GROWTH_FACTOR` | — | `missing` |
| `EXECUTION_LOGGING_ENABLED` | — | `missing` |
| `EXECUTION_LOG_MAX_CHARS` | — | `missing` |
| `EXECUTION_LOG_USE_COLOR` | — | `missing` |
| `CHILD_CHUNK_SIZE` | — | `missing` |
| `CHILD_CHUNK_OVERLAP` | — | `missing` |
| `MIN_PARENT_SIZE` | — | `missing` |
| `MAX_PARENT_SIZE` | — | `missing` |
| `HEADERS_TO_SPLIT_ON` | — | `missing` |
| `LANGFUSE_ENABLED` | — | `missing` |
| `LANGFUSE_PUBLIC_KEY` | — | `missing` |
| `LANGFUSE_SECRET_KEY` | — | `missing` |
| `LANGFUSE_BASE_URL` | — | `missing` |

---

## Summary Statistics

*Counts verified against the per-entry Status fields during E-001 acceptance.*

### Section 1.5 baseline capabilities (17 total)
| Status | Count | Items |
|---|---|---|
| `implemented` | 0 | — |
| `scaffold` | 8 | PDF/MD ingestion (#1), parent-child chunking (#2), child/parent retrieval (#3), self-correcting retrieval loop (#10), budget limits (#12), fallback answer (#13), Langfuse (#15), RAGAS eval (#17) |
| `missing` | 9 | Qdrant hybrid (#4), conversation memory (#5), query rewriting (#6), clarification/HITL (#7), parallel agent (#8), tool calling (#9), context compression (#11), answer aggregation (#14), Gradio UI (#16) |

### Section 3.3 must-retain execution symbols (16 total)
| Status | Count | Items |
|---|---|---|
| `implemented` | 0 | — |
| `scaffold` | 3 | `fallback_response`, `MAX_TOOL_CALLS`, `MAX_ITERATIONS` |
| `missing` | 13 | `summarize_history`, `rewrite_query`, `request_clarification`, `orchestrator`, `should_compress_context`, `compress_context`, `collect_answer`, `aggregate_answers`, `search_child_chunks`, `retrieve_parent_chunks`, `ToolNode`, `InMemorySaver`, `GRAPH_RECURSION_LIMIT` |

### Configuration key mapping (upstream: 34 keys total)
| Status | Count |
|---|---|
| Target has compatible key | 3 (`max_tool_calls`, `max_iterations`, `max_retrieval_top_k`) |
| Target has incompatible key | 1 (`llm_provider` ↔ `LLM_MODEL`) |
| Target missing | 30 |

### Target-only scaffolds (7)
`AgenticRagState`, `CorpusRegistry`, `AccessPolicy`, `FastAPI entry`, `PlannerAgent`, `SufficientContextAgent`, `SynthesisAgent`

### Key Compatibility Risks
1. **LangGraph absent**: Target `AgenticRagRuntime` is a plain Python loop, not a LangGraph state machine. All upstream orchestration (interrupts, Send, conditional edges, ToolNode) is lost.
2. **No vector DB**: Target has Qdrant config but no `VectorDbManager` or Qdrant integration. Retrieval is mock-only.
3. **No parent-child chunking**: Target `SimpleChunker` lacks heading-aware splitting, parent/child hierarchy, metadata propagation.
4. **Config semantics diverge**: `max_iterations` (3 target vs 10 upstream) and `max_tool_calls` (12 target vs 8 upstream) have different meanings.
5. **No conversation memory**: Target state has no `conversation_summary`, `pendingQuery`, or bounded history fields.
6. **No Gradio UI**: Target only has FastAPI; Gradio tab-based document management and chat are missing.
7. **No Langfuse**: Target `TraceRecorder` is in-memory only; upstream has full Langfuse `CallbackHandler` integration.
