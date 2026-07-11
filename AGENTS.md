# AGENTS.md — Agentic RAG Enterprise

## Implementation Spec
`docs/agentic-rag-enterprise-build-plan.md`

## Current Milestone & Issue
- Milestone: **M0** — Repository Reconciliation & Baseline
- Issue: **E-M0C** — Milestone 0 Closure: exit gate compliance

## Fixed Paths
```bash
UPSTREAM_REPO=/vol4/Agent/agentic-rag-for-dummies
TARGET_REPO=/vol4/Agent/agentic-rag-enterprise
```

## Fixed Commits (M0 baseline)
- Target: `6e80b31614d127c4f004e60edcf4d3935653bd2a` (main)
- Upstream: `8b3e5ff0619f7ede593d728e4a8b459fbbec9b08` (main, tag v2.3)

## Permanent Rules (all milestones)
1. **DO NOT modify upstream** (`/vol4/Agent/agentic-rag-for-dummies/`).
2. Target uses `src/agentic_rag_enterprise/` package layout.
3. `pyproject.toml` is the single source of truth for dependencies.
4. Do not create empty code directories.
5. Keep existing working tree changes; do not reset, checkout, or overwrite.

## E-M0C Allowed Changes (closure only)
- All previously created M0 deliverables may be staged and committed.
- `src/agentic_rag_enterprise/graph/runtime.py` — fix str|None type mismatch
- `pyproject.toml` — add types-PyYAML, freeze Python 3.13, update ruff target
- `.python-version` — create
- `docs/baseline-validation.md` — update Python freeze record
- `uv.lock` — regenerate
- No modifications to upstream.
- No push, no PR creation.
- One commit only: `chore: close milestone 0 baseline`

## Staging Allowlist (git add)
```
.python-version
AGENTS.md
UPSTREAM.md
pyproject.toml
uv.lock
docs/agentic-rag-enterprise-build-plan.md
docs/baseline-validation.md
docs/upstream-capability-map.md
src/agentic_rag_enterprise/providers.py
src/agentic_rag_enterprise/graph/runtime.py
tests/baseline/
```

## Standard Checks
```bash
# Before starting a task
cd $TARGET_REPO
git status --short
git branch --show-current
git rev-parse HEAD

cd $UPSTREAM_REPO
git status --short
git rev-parse HEAD

# After completing a task
cd $TARGET_REPO
git diff --check
git status --short
```
