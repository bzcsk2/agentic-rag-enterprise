"""Unit tests for the parent-child chunker (E-007).

Focus: heading-aware splitting, parent size constraints (merge small /
split large), child-to-parent integrity, provenance, and **stable,
content-addressed, non-filename parent IDs**.
"""

import re

from agentic_rag_enterprise.ingestion.chunker import (
    DEFAULT_MAX_PARENT_SIZE,
    DEFAULT_MIN_PARENT_SIZE,
    ParentChildChunker,
)

_MD = """# Title

Intro paragraph describing the system at a high level.

## Section A

{body}

## Section B

{body}
"""


def _body(n: int) -> str:
    return "Word " * n


def test_heading_aware_section_paths() -> None:
    # Each chapter carries enough content to clear MIN_PARENT_SIZE, so the
    # two H2 sections are kept as *separate* parents (no small-parent merge).
    # This verifies headers are captured into section_path per segment.
    md = "# Book\n\n## Chapter 1\n\n" + _body(450) + "\n\n## Chapter 2\n\n" + _body(450) + "\n"
    chunker = ParentChildChunker()
    parents, _ = chunker.chunk_markdown(md, tenant_id="t1", corpus_id="c1", document_id="d1")
    paths = [tuple(p.section_path) for p in parents]
    assert ("Book", "Chapter 1") in paths
    assert ("Book", "Chapter 2") in paths


def test_merge_small_parents() -> None:
    # Two short H2 sections + intro, total content well above MIN, should
    # merge into a single parent rather than keep tiny fragments. The merged
    # parent must clear MIN_PARENT_SIZE.
    md = _MD.format(body=_body(300))  # ~ generous content, all short sections
    chunker = ParentChildChunker()
    parents, _ = chunker.chunk_markdown(md, tenant_id="t1", corpus_id="c1", document_id="d1")
    assert len(parents) == 1
    assert len(parents[0].text) >= DEFAULT_MIN_PARENT_SIZE


def test_split_large_parent() -> None:
    # One H1 section far larger than MAX must be split into multiple parents.
    big = _body(800)  # ~4800 chars
    md = f"# Big\n\n{big}\n"
    chunker = ParentChildChunker()
    parents, _ = chunker.chunk_markdown(md, tenant_id="t1", corpus_id="c1", document_id="d1")
    assert len(parents) >= 2
    assert all(len(p.text) <= DEFAULT_MAX_PARENT_SIZE for p in parents)


def test_child_parent_integrity() -> None:
    md = _MD.format(body=_body(200))
    chunker = ParentChildChunker()
    parents, children = chunker.chunk_markdown(md, tenant_id="t1", corpus_id="c1", document_id="d1")
    parent_ids = {p.parent_id for p in parents}
    assert children
    for child in children:
        assert child.parent_id in parent_ids
        parent = next(p for p in parents if p.parent_id == child.parent_id)
        assert child.section_path == parent.section_path
        assert child.document_id == parent.document_id
        assert child.tenant_id == parent.tenant_id
        assert child.corpus_id == parent.corpus_id


def test_stable_and_content_addressed_ids() -> None:
    md = _MD.format(body=_body(200))
    chunker = ParentChildChunker()
    p1, c1 = chunker.chunk_markdown(md, tenant_id="t1", corpus_id="c1", document_id="d1")
    p2, c2 = chunker.chunk_markdown(md, tenant_id="t1", corpus_id="c1", document_id="d1")
    # Deterministic.
    assert [p.parent_id for p in p1] == [p.parent_id for p in p2]
    assert [c.child_id for c in c1] == [c.child_id for c in c2]
    # Not filename-derived: pure 16-char hex, never "{stem}_p{i}".
    assert all(re.fullmatch(r"[0-9a-f]{16}", p.parent_id) for p in p1)
    assert all("_p" not in p.parent_id for p in p1)
    # Different content -> different id.
    p3, _ = chunker.chunk_markdown(
        "# Other\n\ncompletely different content here.\n",
        tenant_id="t1",
        corpus_id="c1",
        document_id="d1",
    )
    assert p3[0].parent_id != p1[0].parent_id


def test_tenant_scoped_ids_differ() -> None:
    md = "# Doc\n\nsome content.\n"
    chunker = ParentChildChunker()
    a, _ = chunker.chunk_markdown(md, tenant_id="t1", corpus_id="c1", document_id="d1")
    b, _ = chunker.chunk_markdown(md, tenant_id="t2", corpus_id="c1", document_id="d1")
    assert a[0].parent_id != b[0].parent_id


def test_provenance_metadata_present() -> None:
    md = "# Book\n\n## Chapter 1\n\ntext.\n"
    chunker = ParentChildChunker()
    parents, children = chunker.chunk_markdown(md, tenant_id="t9", corpus_id="c9", document_id="d9")
    assert parents[0].tenant_id == "t9"
    assert parents[0].corpus_id == "c9"
    assert parents[0].document_id == "d9"
    assert children[0].tenant_id == "t9"


def test_simple_chunker_adapter_unchanged() -> None:
    # Backward-compatible mock adapter must still work (baseline).
    from agentic_rag_enterprise.ingestion.chunker import SimpleChunker

    chunks = SimpleChunker().chunk("doc", "hello world this is text", size=5)
    assert len(chunks) == 5
    assert all(c.parent_id == "doc" for c in chunks)
