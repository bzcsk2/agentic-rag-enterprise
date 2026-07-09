# Architecture

`agentic-rag-enterprise` treats RAG as a bounded, auditable agent runtime.

## Runtime loop

```text
normalize query
  -> plan required facts
  -> route subquestions to corpora
  -> retrieve evidence
  -> judge sufficient context
  -> continue retrieval or synthesize
  -> emit answer, citations, trace, and stop reason
```

## Main components

### Planner Agent

Creates a structured plan with required facts, subquestions, target corpora, and dependency hints.

### Corpus Router

Uses corpus descriptions and metadata to select the correct knowledge source. Corpus descriptions are routing assets and should be maintained with the same care as API contracts.

### Retriever

Starts as a mock interface. The production implementation should support:

- dense retrieval;
- sparse retrieval;
- hybrid scoring;
- metadata filters;
- parent-child chunk expansion;
- reranking;
- permission-aware retrieval.

### Sufficient Context Agent

Judges whether the retrieved evidence contains all facts required to answer the user query. The decision must be structured and include:

- sufficiency status;
- covered facts;
- missing facts;
- contradictions;
- next queries;
- target corpora;
- reason.

### Iteration Controller

Controls bounded search with max iterations, max tool calls, visited-query cache, visited-document cache, and explicit stop reasons.

### Grounded Synthesis Agent

Produces final answers only from retrieved evidence. When evidence is insufficient, it should abstain rather than hallucinate.

## Production principles

- The context window is not runtime state.
- Retrieval permissions must be enforced before evidence enters model context.
- Every final claim should map to supporting evidence.
- Iteration must be bounded by cost, latency, and risk.
- Evaluation must include answerable, multi-hop, cross-corpus, and unanswerable cases.
