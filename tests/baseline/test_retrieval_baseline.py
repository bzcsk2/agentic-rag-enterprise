"""Baseline characterization tests for retrieval scaffold, corpus registry,
security policy, and evaluation metrics.

All implementations are deterministic mocks with no external dependencies.
"""

from pathlib import Path

import pytest

from agentic_rag_enterprise.evals.metrics import citation_coverage, EvalResult
from agentic_rag_enterprise.retrieval.corpus_registry import CorpusRegistry
from agentic_rag_enterprise.retrieval.retriever import Retriever
from agentic_rag_enterprise.schemas import CorpusConfig, Evidence
from agentic_rag_enterprise.security.policy import AccessPolicy


# --- Retriever ---


def test_mock_retriever_returns_single_evidence() -> None:
    retriever = Retriever()
    results = retriever.retrieve("test query", ["default"])
    assert len(results) == 1
    ev = results[0]
    assert isinstance(ev, Evidence)
    assert ev.evidence_id == "mock-evidence-1"
    assert ev.corpus_id == "default"
    assert ev.document_id == "mock-doc"
    assert ev.score == 1.0


def test_mock_retriever_includes_query_in_text() -> None:
    retriever = Retriever()
    results = retriever.retrieve("hello world", ["default"])
    assert "hello world" in results[0].text


def test_mock_retriever_respects_top_k() -> None:
    retriever = Retriever()
    results = retriever.retrieve("q", ["default"], top_k=0)
    assert len(results) == 0


def test_mock_retriever_defaults_corpus() -> None:
    retriever = Retriever()
    results = retriever.retrieve("q", [])
    assert results[0].corpus_id == "default"


def test_mock_retriever_first_corpus_used() -> None:
    retriever = Retriever()
    results = retriever.retrieve("q", ["corpus_a", "corpus_b"])
    assert results[0].corpus_id == "corpus_a"


# --- CorpusRegistry ---


def test_corpus_registry_empty() -> None:
    registry = CorpusRegistry()
    assert registry.list() == []


def test_corpus_registry_list() -> None:
    config = CorpusConfig(
        corpus_id="docs", name="Docs", description="documents", collection_name="docs_coll"
    )
    registry = CorpusRegistry([config])
    assert len(registry.list()) == 1
    assert registry.list()[0].corpus_id == "docs"


def test_corpus_registry_get() -> None:
    config = CorpusConfig(
        corpus_id="wiki", name="Wiki", description="wiki pages", collection_name="wiki_coll"
    )
    registry = CorpusRegistry([config])
    retrieved = registry.get("wiki")
    assert retrieved.corpus_id == "wiki"
    assert retrieved.name == "Wiki"


def test_corpus_registry_get_raises_on_unknown() -> None:
    registry = CorpusRegistry()
    with pytest.raises(KeyError):
        registry.get("nonexistent")


def test_corpus_registry_describe_for_planner() -> None:
    config = CorpusConfig(
        corpus_id="docs", name="Docs", description="engineering docs", collection_name="docs_coll"
    )
    registry = CorpusRegistry([config])
    desc = registry.describe_for_planner()
    assert "docs: engineering docs" in desc


def test_corpus_registry_describe_empty() -> None:
    registry = CorpusRegistry()
    assert registry.describe_for_planner() == ""


def test_corpus_registry_from_yaml(tmp_path: Path) -> None:
    yaml_content = """corpora:
  - corpus_id: "eng"
    name: "Engineering Wiki"
    description: "engineering docs"
    collection_name: "eng_coll"
"""
    yaml_path = tmp_path / "corpora.yaml"
    yaml_path.write_text(yaml_content)
    registry = CorpusRegistry.from_yaml(str(yaml_path))
    assert len(registry.list()) == 1
    assert registry.get("eng").name == "Engineering Wiki"


# --- AccessPolicy ---


def test_access_policy_allows_without_policy() -> None:
    policy = AccessPolicy()
    corpus = CorpusConfig(
        corpus_id="test",
        name="Test",
        description="test",
        collection_name="test_coll",
    )
    assert policy.can_access("user1", corpus) is True


def test_access_policy_denies_unlisted_user() -> None:
    policy = AccessPolicy()
    corpus = CorpusConfig(
        corpus_id="test",
        name="Test",
        description="test",
        collection_name="test_coll",
        access_policy={"allowed_users": ["alice", "bob"]},
    )
    assert policy.can_access("charlie", corpus) is False


def test_access_policy_allows_listed_user() -> None:
    policy = AccessPolicy()
    corpus = CorpusConfig(
        corpus_id="test",
        name="Test",
        description="test",
        collection_name="test_coll",
        access_policy={"allowed_users": ["alice", "bob"]},
    )
    assert policy.can_access("alice", corpus) is True


# --- citation_coverage ---


def test_citation_coverage_empty_required() -> None:
    result = citation_coverage([], [])
    assert result.score == 1.0
    assert isinstance(result, EvalResult)


def test_citation_coverage_full_coverage() -> None:
    result = citation_coverage(["a", "b", "c"], ["a", "b", "c"])
    assert result.score == 1.0


def test_citation_coverage_partial() -> None:
    result = citation_coverage(["a", "b"], ["a", "b", "c"])
    assert result.score == pytest.approx(2 / 3)


def test_citation_coverage_no_coverage() -> None:
    result = citation_coverage(["d"], ["a", "b"])
    assert result.score == 0.0


def test_citation_coverage_duplicates_handled() -> None:
    result = citation_coverage(["a", "a", "b"], ["a", "b", "c"])
    assert result.score == pytest.approx(2 / 3)
