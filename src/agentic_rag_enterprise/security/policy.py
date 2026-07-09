from agentic_rag_enterprise.schemas import CorpusConfig


class AccessPolicy:
    """Retrieval-time access control placeholder.

    Enterprise RAG permissions must be enforced before retrieval results reach
    the model context. UI-only filtering is not sufficient.
    """

    def can_access(self, user_id: str, corpus: CorpusConfig) -> bool:
        allowed_users = corpus.access_policy.get("allowed_users")
        if not allowed_users:
            return True
        return user_id in allowed_users
