"""Policy enforcement point (PEP): derive Qdrant filters from the PDP.

The filter encodes exactly the truth table in
:func:`agentic_rag_enterprise.security.policy.evaluate_access`. The model
never chooses which corpora to search or which ACL fields to trust; the
runtime computes the filter from the current :class:`SecurityContext` and
injects it into every retrieval call.
"""

from qdrant_client.models import Condition, FieldCondition, Filter, MatchAny, MatchValue

from agentic_rag_enterprise.domain.security import SecurityContext
from agentic_rag_enterprise.security.policy import (
    AuthorizationDecision,
    evaluate_access,
    ResourceAcl,
)


def _fail_closed(key: str) -> FieldCondition:
    """A condition that can never match.

    Qdrant treats an empty ``MatchAny(any=[])`` as matching everything, which
    would *broaden* access. For an empty allow-list we instead use a sentinel
    value that is guaranteed absent, so the filter fails closed.
    """
    return FieldCondition(key=key, match=MatchValue(value="\x00__no_match__\x00"))


def build_access_filter(ctx: SecurityContext, corpus_id: str) -> Filter:
    """Build a Qdrant ``Filter`` enforcing the access truth table.

    Encodes: tenant match, active status, allowed security levels, and the
    tenant/restricted scope allow/deny logic, with deny precedence.

    Empty allow-lists fail closed: an empty ``allowed_security_levels`` adds an
    unsatisfiable ``must`` condition (zero results), and an empty ``groups``
    makes the group-allow branch unsatisfiable while tenant/user branches
    still apply.
    """
    levels = list(ctx.allowed_security_levels)
    groups = list(ctx.groups)

    security_level_cond: Condition = (
        FieldCondition(key="security_level", match=MatchAny(any=levels))
        if levels
        else _fail_closed("security_level")
    )
    group_cond: Condition = (
        FieldCondition(key="allowed_group_ids", match=MatchAny(any=groups))
        if groups
        else _fail_closed("allowed_group_ids")
    )

    must: list[Condition] = [
        FieldCondition(key="tenant_id", match=MatchValue(value=ctx.tenant_id)),
        FieldCondition(key="corpus_id", match=MatchValue(value=corpus_id)),
        FieldCondition(key="status", match=MatchValue(value="active")),
        FieldCondition(key="deprecated", match=MatchValue(value=False)),
        security_level_cond,
        Filter(
            should=[
                FieldCondition(key="acl_scope", match=MatchValue(value="tenant")),
                FieldCondition(
                    key="allowed_user_ids",
                    match=MatchAny(any=[ctx.user_id]),
                ),
                group_cond,
            ],
        ),
    ]

    must_not: list[Condition] = [
        FieldCondition(
            key="denied_user_ids",
            match=MatchAny(any=[ctx.user_id]),
        ),
        FieldCondition(
            key="denied_group_ids",
            match=MatchAny(any=list(ctx.groups)),
        ),
    ]

    return Filter(must=must, must_not=must_not)


def resource_passes_filter(
    ctx: SecurityContext,
    acl: ResourceAcl,
    status: str = "active",
    deprecated: bool = False,
) -> bool:
    """Cheap, Qdrant-free projection of :func:`build_access_filter`.

    Useful for pre-flight checks (e.g. parent-store second-pass
    authorization) where the resource is already loaded. A deprecated or
    non-active resource never passes, mirroring the Qdrant ``must`` filter.
    """

    if status != "active" or deprecated:
        return False
    return evaluate_access(ctx, acl) is AuthorizationDecision.ALLOW
