# agentic-rag-enterprise

Enterprise-grade Agentic RAG runtime inspired by Gemini Enterprise Agent Platform's Agentic RAG architecture.

This repository is a Python-first implementation blueprint for building dependable, auditable, multi-corpus RAG systems. It focuses on **planning, corpus routing, iterative retrieval, sufficient-context checking, grounded synthesis, traceability, and evaluation** rather than a simple "vector search + LLM answer" demo.

> Current repository name on GitHub may still be `advance-prompt-zh`. Rename it in GitHub Settings to `agentic-rag-enterprise` after this migration.

## Why this project exists

Traditional RAG often fails in enterprise settings because the retrieved context can be relevant but still incomplete. This project treats RAG as an agent runtime problem:

- the system must plan what facts are required;
- route subqueries to the right corpora;
- retrieve, rerank, and consolidate evidence;
- judge whether the current context is sufficient;
- continue searching when evidence is incomplete;
- abstain when the answer cannot be grounded;
- preserve a full trace for review, replay, and evaluation.

## Target architecture

```text
User Query
   ↓
Root Orchestrator
   ├── Query Normalizer
   ├── Planner Agent
   ├── Corpus Router
   ├── Query Rewriter
   ├── Search Fanout
   ├── Evidence Store
   ├── Sufficient Context Agent
   ├── Iteration Controller
   └── Grounded Synthesis Agent
   ↓
Auditable Answer + Citations + Trace
```

## Core capabilities

- **Corpus Registry**: structured descriptions, ownership, metadata, and ACL boundaries for each enterprise knowledge source.
- **Planner / Router**: decomposes user questions and routes subqueries to the right corpora.
- **Hybrid Retrieval**: dense + sparse retrieval with metadata filtering and reranking hooks.
- **Sufficient Context Agent**: judges whether retrieved evidence is enough to answer; emits missing facts and next queries.
- **Iterative Retrieval Loop**: bounded loop with max iterations, max tool calls, visited-query cache, and stop reasons.
- **Grounded Synthesis**: answers only from evidence, with citation maps and abstention support.
- **Evaluation Harness**: tests retrieval quality, answer faithfulness, sufficiency detection, and refusal behavior.
- **Observability**: records plans, tool calls, evidence sets, sufficiency decisions, cost, latency, and final claims.

## Repository layout

```text
agentic-rag-enterprise/
  src/agentic_rag_enterprise/
    agents/              # planner, router, SCA, synthesis
    api/                 # FastAPI service
    evals/               # benchmark cases and metrics
    graph/               # LangGraph-compatible runtime state and orchestration
    ingestion/           # parsing, chunking, indexing
    observability/       # traces, evidence store, citation map
    retrieval/           # corpus registry, retriever, reranker
    security/            # ACL filter and prompt-injection checks
  docs/
    architecture.md
  examples/
    corpora.yaml
  tests/
```

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
make test
```

Run the API service:

```bash
uvicorn agentic_rag_enterprise.api.main:app --reload
```

## Development status

This repository is currently a scaffold for the enterprise Agentic RAG runtime. The first milestone is to implement a minimal loop:

1. register corpora;
2. plan a question;
3. route subqueries;
4. retrieve evidence;
5. judge sufficient context;
6. synthesize a grounded answer;
7. record trace and evaluation artifacts.

## Design principle

RAG is not just retrieval. Enterprise Agentic RAG needs runtime governance: state, traces, permission boundaries, evidence sufficiency, bounded iteration, and evaluation feedback loops.

## License

MIT
