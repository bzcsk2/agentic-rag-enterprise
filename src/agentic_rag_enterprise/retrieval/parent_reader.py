"""Parent-chunk second authorization.

Given an authorized child :class:`RetrievalHit`, load the referenced parent and
re-establish **all** enterprise authorization boundaries before returning it.

This is the ONLY authorized way to obtain a parent. There is deliberately no
public ``load_parent(parent_id)`` entry point: a model- or tool-supplied parent
id must never skip these checks (E-007 contract).
"""

from typing import Any

from agentic_rag_enterprise.domain.security import SecurityContext
from agentic_rag_enterprise.retrieval.models import (
    AuthorizedParent,
    ParentAuthorizationError,
    RetrievalHit,
    as_acl_scope,
)
from agentic_rag_enterprise.security.filter import resource_passes_filter
from agentic_rag_enterprise.security.policy import ResourceAcl
from agentic_rag_enterprise.storage.parent_store import ParentStore


def _acl_from_record(record: dict[str, Any], tenant_id: str) -> ResourceAcl:
    return ResourceAcl(
        tenant_id=tenant_id,
        security_level=str(record.get("security_level", "public")),
        acl_scope=as_acl_scope(record.get("acl_scope", "restricted")),
        allowed_user_ids=[str(v) for v in (record.get("allowed_user_ids") or [])],
        allowed_group_ids=[str(v) for v in (record.get("allowed_group_ids") or [])],
        denied_user_ids=[str(v) for v in (record.get("denied_user_ids") or [])],
        denied_group_ids=[str(v) for v in (record.get("denied_group_ids") or [])],
    )


def _record_acl_equal(a: dict[str, Any], b: dict[str, Any]) -> bool:
    keys = (
        "security_level",
        "acl_scope",
        "allowed_user_ids",
        "allowed_group_ids",
        "denied_user_ids",
        "denied_group_ids",
    )
    for k in keys:
        if a.get(k) != b.get(k):
            return False
    return True


class ParentReader:
    """Loads and second-authorizes parents for authorized child hits."""

    def __init__(self, parent_store: ParentStore) -> None:
        self._store = parent_store

    def load_parent_for_hit(self, hit: RetrievalHit, ctx: SecurityContext) -> AuthorizedParent:
        parent = self._store.get(hit.parent_id)
        if parent is None:
            raise ParentAuthorizationError(
                "parent id absent from store (guessed or untrusted id?)",
                parent_id=hit.parent_id,
            )

        # Identity consistency: child and parent must agree on the resource.
        # (The child was already tenant-filtered by build_access_filter; this
        # re-verifies the stored parent has not diverged from the child.)
        if hit.tenant_id != parent.tenant_id:
            raise ParentAuthorizationError("child/parent tenant mismatch", hit.parent_id)
        if parent.tenant_id != ctx.tenant_id:
            raise ParentAuthorizationError("tenant mismatch", hit.parent_id)
        if parent.corpus_id != hit.corpus_id:
            raise ParentAuthorizationError("corpus mismatch", hit.parent_id)
        if parent.document_id != hit.document_id:
            raise ParentAuthorizationError("document identity mismatch", hit.parent_id)
        if parent.document_version != hit.document_version:
            raise ParentAuthorizationError("document version mismatch", hit.parent_id)

        md = parent.metadata
        status = str(md.get("status", "active"))
        deprecated = bool(md.get("deprecated", False))

        # Lifecycle gate.
        if status != "active" or deprecated:
            raise ParentAuthorizationError(
                f"parent lifecycle invalid (status={status}, deprecated={deprecated})",
                hit.parent_id,
            )

        # ACL metadata consistency: the stored parent's ACL must match the
        # child's authorized ACL. A divergence is treated as a mismatch and
        # fails closed.
        parent_acl_record: dict[str, Any] = {
            "security_level": md.get("security_level", "public"),
            "acl_scope": md.get("acl_scope", "restricted"),
            "allowed_user_ids": md.get("allowed_user_ids", []),
            "allowed_group_ids": md.get("allowed_group_ids", []),
            "denied_user_ids": md.get("denied_user_ids", []),
            "denied_group_ids": md.get("denied_group_ids", []),
        }
        hit_acl_record: dict[str, Any] = {
            "security_level": hit.security_level,
            "acl_scope": hit.acl_scope,
            "allowed_user_ids": hit.allowed_user_ids,
            "allowed_group_ids": hit.allowed_group_ids,
            "denied_user_ids": hit.denied_user_ids,
            "denied_group_ids": hit.denied_group_ids,
        }
        if not _record_acl_equal(parent_acl_record, hit_acl_record):
            raise ParentAuthorizationError("parent/child ACL mismatch", hit.parent_id)

        # Second authorization pass via the canonical PDP projection.
        acl = _acl_from_record(parent_acl_record, parent.tenant_id)
        if not resource_passes_filter(ctx, acl, status, deprecated):
            raise ParentAuthorizationError("resource_passes_filter denied", hit.parent_id)

        acl_scope = as_acl_scope(parent_acl_record["acl_scope"])
        security_level = str(parent_acl_record["security_level"])
        allowed_user_ids = [str(v) for v in (parent_acl_record["allowed_user_ids"] or [])]
        allowed_group_ids = [str(v) for v in (parent_acl_record["allowed_group_ids"] or [])]
        denied_user_ids = [str(v) for v in (parent_acl_record["denied_user_ids"] or [])]
        denied_group_ids = [str(v) for v in (parent_acl_record["denied_group_ids"] or [])]

        return AuthorizedParent(
            parent_id=parent.parent_id,
            document_id=parent.document_id,
            document_version=parent.document_version,
            corpus_id=parent.corpus_id,
            tenant_id=parent.tenant_id,
            content=parent.text,
            section_path=parent.section_path,
            metadata=parent.metadata,
            status=status,
            deprecated=deprecated,
            security_level=security_level,
            acl_scope=acl_scope,
            allowed_user_ids=allowed_user_ids,
            allowed_group_ids=allowed_group_ids,
            denied_user_ids=denied_user_ids,
            denied_group_ids=denied_group_ids,
        )
