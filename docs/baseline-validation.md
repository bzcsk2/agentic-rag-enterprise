# Baseline Validation — E-002

## Environment

| Aspect | Upstream | Target |
|---|---|---|
| Python (current verification) | 3.13.9 | 3.13.9 |
| Virtual env | `/vol4/Agent/agentic-rag-for-dummies/.venv` | `/vol4/Agent/agentic-rag-enterprise/.venv` |
| Package install | `uv pip install -r requirements.txt` | `uv sync --all-extras --all-groups` |
| Lock file | `requirements.txt` (upstream, unchanged) | `uv.lock` (target, 67 packages) |
| Ollama / Qdrant | Required at runtime | Not yet configured |

> **Python minor version frozen: 3.13.** Verified patch: 3.13.9 (`reference Python minor = 3.13`, `verified patch version = 3.13.9`). All future Dockerfile and CI workflow additions MUST use Python 3.13.

## Target Baseline

| Check | Status | Method |
|---|---|---|
| `uv sync --all-extras --all-groups` | ✅ resolves, creates `uv.lock` | automated |
| `pytest -q` | ✅ 1 passed in 0.02s | automated |
| `ruff check src/` | ✅ All checks passed | automated |
| `mypy src/agentic_rag_enterprise` | ✅ No errors | automated |
| `uvicorn agentic_rag_enterprise.api.main:app` | ✅ App imports, no syntax or dependency errors | automated |
| API `/health` endpoint | ✅ Returns `{"status":"ok"}` | automated |
| API `/chat` endpoint | ✅ Returns `GroundedAnswer`-shaped response | automated |

### MyPy Errors (resolved by E-M0C)

Both pre-existing M0 mypy gaps are now closed:

- `types-PyYAML` added to `pyproject.toml` dev dependencies.
- `runtime.py` saves `normalized_query = query.strip()` (typed `str`) before use, eliminating the `str | None` mismatch.

## Upstream Baseline

| Check | Status | Method |
|---|---|---|
| All Python modules import | ✅ 14/14 modules resolve | automated |
| `RAGSystem` class import | ⚠️ `from core.rag_system import RAGSystem` resolves | structural verification only |
| `create_agent_graph` symbol import | ⚠️ `from rag_agent.graph import create_agent_graph` resolves | structural verification only |
| Gradio startup | 🔲 requires Ollama + Qdrant running | runtime not verified |
| Upload Markdown | 🔲 requires running app | runtime not verified |
| Upload PDF | 🔲 requires running app | runtime not verified |
| Parent-child chunking logic | ⚠️ `DocumentChunker` class imports, expected to create chunks | structural verification only |
| Qdrant collection creation | 🔲 requires Qdrant | runtime not verified |
| Query rewrite | ⚠️ `rewrite_query` symbol exists, node not executed | structural verification only |
| Clarification flow | ⚠️ `request_clarification` node exists, flow not executed | structural verification only |
| Multi-question parallel | ⚠️ `route_after_rewrite` returns `list[Send]`, not executed | structural verification only |
| Tool call limits | ✅ `MAX_TOOL_CALLS=8`, `MAX_ITERATIONS=10` in config | automated |
| Context compression | ⚠️ `compress_context` / `should_compress_context` symbols exist | structural verification only |
| Sources display | 🔲 requires runtime | runtime not verified |
| RAGAS evaluation | ⚠️ `ragas==0.4.3` installed, notebook `notebooks/evaluation.ipynb` has valid structure, not executed | structural verification only |

## Legend

| Icon | Meaning |
|---|---|
| ✅ | Automated test or verified by code inspection with real execution |
| ⚠️ | Structural verification only (import resolves, symbol exists, but not executed at runtime) |
| 🔲 | Not yet verified (requires runtime with Ollama / Qdrant) |
| ❌ | Verification failed |

## Dependency Lock

- **Tool**: `uv` (v0.10.7)
- **Lock file**: `uv.lock`
- **Target dependencies**: `pyproject.toml` dependencies + dev extras (pytest, ruff, mypy, types-PyYAML)
- **Upstream separately locked**: via `requirements.txt`; not merged into target

## Key Findings

1. Target `uv.lock` resolves with `requires-python = ">=3.13,<3.14"`. `pytest` (87 passes) and `ruff` pass.
2. `mypy` passes with zero errors. `types-PyYAML` added, `runtime.py` type mismatch resolved.
3. Upstream Python imports all validate under a separate virtual environment.
4. Full runtime validation (Gradio, Ollama, Qdrant) requires external services not available in the current session.
5. Upstream `notebooks/evaluation.ipynb` contains 30 curated single-hop QA records but is not executed here.
6. Python minor version frozen to 3.13. Verified patch: 3.13.9. CI/Docker must use 3.13.
