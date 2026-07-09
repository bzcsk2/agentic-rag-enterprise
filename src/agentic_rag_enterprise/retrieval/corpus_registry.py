from pathlib import Path

import yaml

from agentic_rag_enterprise.schemas import CorpusConfig


class CorpusRegistry:
    """In-memory registry for enterprise corpora.

    Corpus descriptions are first-class routing assets. They should explain what
    a corpus contains, what questions it can answer, and what it should not be
    used for.
    """

    def __init__(self, corpora: list[CorpusConfig] | None = None) -> None:
        self._corpora = {item.corpus_id: item for item in corpora or []}

    @classmethod
    def from_yaml(cls, path: str | Path) -> "CorpusRegistry":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        corpora = [CorpusConfig(**item) for item in data.get("corpora", [])]
        return cls(corpora)

    def list(self) -> list[CorpusConfig]:
        return list(self._corpora.values())

    def get(self, corpus_id: str) -> CorpusConfig:
        return self._corpora[corpus_id]

    def describe_for_planner(self) -> str:
        return "\n".join(
            f"- {c.corpus_id}: {c.description}" for c in self._corpora.values()
        )
