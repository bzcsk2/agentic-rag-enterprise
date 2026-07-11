"""Baseline characterization tests for SimpleChunker.

Locks down the current scaffold behavior before parent-child chunking is ported from upstream.
"""

from agentic_rag_enterprise.ingestion.chunker import Chunk, SimpleChunker


def test_chunker_empty_text() -> None:
    chunker = SimpleChunker()
    result = chunker.chunk("doc0", "", size=100)
    assert result == []


def test_chunker_single_chunk() -> None:
    chunker = SimpleChunker()
    result = chunker.chunk("doc1", "hello world", size=100)
    assert len(result) == 1
    chunk = result[0]
    assert chunk.chunk_id == "doc1:0"
    assert chunk.parent_id == "doc1"
    assert chunk.text == "hello world"
    assert chunk.metadata == {"document_id": "doc1"}


def test_chunker_splits_on_size_boundary() -> None:
    chunker = SimpleChunker()
    text = "a" * 50 + "b" * 50
    result = chunker.chunk("doc2", text, size=50)
    assert len(result) == 2
    assert result[0].text == "a" * 50
    assert result[1].text == "b" * 50


def test_chunker_chunk_id_sequential() -> None:
    chunker = SimpleChunker()
    text = "x" * 300
    result = chunker.chunk("doc3", text, size=100)
    assert len(result) == 3
    assert result[0].chunk_id == "doc3:0"
    assert result[1].chunk_id == "doc3:1"
    assert result[2].chunk_id == "doc3:2"


def test_chunk_model_defaults() -> None:
    chunk = Chunk(chunk_id="c1", text="test")
    assert chunk.parent_id is None
    assert chunk.metadata == {}
