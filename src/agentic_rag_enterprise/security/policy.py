"""Policy decision point (PDP) and the access truth table.

The truth table in :func:`evaluate_access` is the single source of authorization
logic for retrieval-time access. Qdrant filters (PEP) must be derived from
this decision, never from a model-chosen corpus list or free-form document
metadata.

Fixed ACL semantics (build plan §11.3):

* ``deny`` always precedes ``allow``, including for admins. Admin bypass is
  only possible through an independent, auditable break-glass policy.
* ``acl_scope == "tenant"`` means every user in the tenant whose
  ``security_level`` is allowed can read the resource.
* ``acl_scope == "restricted"`` with empty allow lists means nobody can read
  it — it does **not** mean public.
* Corpus discoverability and document readability are computed separately;
  the former never substitutes for the latter.
* ``is_admin`` grants no implicit read permission on its own.
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from agentic_rag_enterprise.domain.document import SourceDocument
from agentic_rag_enterprise.domain.security import SecurityContext


class AuthorizationDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class ResourceAcl(BaseModel):
    """ACL attributes a protected resource carries."""

    tenant_id: str
    security_level: str

    acl_scope: Literal["tenant", "restricted"] = "restricted"
    allowed_user_ids: list[str] = Field(default_factory=list)
    allowed_group_ids: list[str] = Field(default_factory=list)
    denied_user_ids: list[str] = Field(default_factory=list)
    denied_group_ids: list[str] = Field(default_factory=list)


def evaluate_access(ctx: SecurityContext, acl: ResourceAcl) -> AuthorizationDecision:
    """Return the canonical allow/deny decision for ``ctx`` on ``acl``.

    Evaluation order is fixed and intentional:
    1. Tenant boundary (hard stop, before anything else).
    2. Deny precedence (user then group), including admins.
    3. Security-level gate.
    4. Scope-based allow (tenant scope, else explicit allow lists).
    """

    # 1. Tenant boundary is the first filter.
    if ctx.tenant_id != acl.tenant_id:
        return AuthorizationDecision.DENY

    # 2. Deny always precedes allow, even for admins.
    if ctx.user_id in acl.denied_user_ids:
        return AuthorizationDecision.DENY
    if set(ctx.groups) & set(acl.denied_group_ids):
        return AuthorizationDecision.DENY

    # 3. Security-level gate.
    if acl.security_level not in ctx.allowed_security_levels:
        return AuthorizationDecision.DENY

    # 4. Scope-based allow.
    if acl.acl_scope == "tenant":
        return AuthorizationDecision.ALLOW

    # acl_scope == "restricted": empty allow lists mean nobody, not public.
    if ctx.user_id in acl.allowed_user_ids:
        return AuthorizationDecision.ALLOW
    if set(ctx.groups) & set(acl.allowed_group_ids):
        return AuthorizationDecision.ALLOW
    return AuthorizationDecision.DENY


def can_discover_corpus(ctx: SecurityContext, corpus_id: str) -> bool:
    """Corpus discoverability is separate from document readability.

    ``None`` ``allowed_corpus_ids`` means "all corpora the runtime knows
    about"; an explicit list restricts discovery to those ids.
    """

    if ctx.allowed_corpus_ids is None:
        return True
    return corpus_id in ctx.allowed_corpus_ids


def can_manage_document(ctx: SecurityContext, doc: SourceDocument) -> bool:
    """Write-authorization for document mutation (update/delete/purge/ACL).

    Fail-closed: a caller may mutate a document only if ALL hold:

    * it is in their tenant,
    * the corpus is discoverable to them,
    * they can already READ the document (the canonical PDP allows the
      document's ACL for ``ctx``), AND
    * they are an explicit OWNER of the document (named in the ACL allow
      lists) or are an admin (auditable break-glass).

    Read access alone is NOT sufficient: a tenant member who can read a shared
    document must not be able to update/delete/purge it or tighten its ACL
    (build plan §10.6/§10.7) — write requires ownership. Cross-tenant and
    non-discoverable corpora are denied outright.
    """
    if ctx.tenant_id != doc.tenant_id:
        return False
    if not can_discover_corpus(ctx, doc.corpus_id):
        return False
    acl = ResourceAcl(
        tenant_id=doc.tenant_id,
        security_level=doc.security_level,
        acl_scope=doc.acl_scope,
        allowed_user_ids=doc.allowed_user_ids,
        allowed_group_ids=doc.allowed_group_ids,
        denied_user_ids=doc.denied_user_ids,
        denied_group_ids=doc.denied_group_ids,
    )
    if evaluate_access(ctx, acl) is not AuthorizationDecision.ALLOW:
        return False
    if ctx.is_admin:
        return True
    if ctx.user_id in doc.allowed_user_ids:
        return True
    if set(ctx.groups) & set(doc.allowed_group_ids):
        return True
    return False


# Canonical restrictiveness order for ``security_level`` (build plan §11.3). A
# higher rank is MORE restrictive (fewer principals can read). Unknown levels
# rank highest so a change toward an unknown level is treated as tightening and a
# change away from one is rejected (fail-closed on widening).
_SECURITY_LEVEL_ORDER: dict[str, int] = {"public": 0, "internal": 1, "secret": 2}


def _security_level_rank(level: str) -> int:
    return _SECURITY_LEVEL_ORDER.get(level, len(_SECURITY_LEVEL_ORDER))


def is_acl_tightening(old: ResourceAcl, new: ResourceAcl) -> bool:
    """Return True iff ``new`` is a *tightening* (never a widening) of ``old``.

    A tightening reduces or preserves access: it must not add allowed principals,
    must not remove denied principals, must not widen ``acl_scope`` (restricted ->
    tenant), and must not lower the ``security_level`` restrictiveness (build
    plan §10.7, "tightening is prioritized over widening"). Any widening is
    rejected so ``tighten_acl`` cannot accidentally grant broader access.
    """
    if new.acl_scope == "tenant" and old.acl_scope == "restricted":
        return False  # restricted -> tenant widens
    if _security_level_rank(new.security_level) < _security_level_rank(old.security_level):
        return False  # less restrictive security level widens
    if not set(new.allowed_user_ids) <= set(old.allowed_user_ids):
        return False  # added an allowed user widens
    if not set(new.allowed_group_ids) <= set(old.allowed_group_ids):
        return False
    if not set(old.denied_user_ids) <= set(new.denied_user_ids):
        return False  # removed a denied user widens
    if not set(old.denied_group_ids) <= set(new.denied_group_ids):
        return False
    return True


class AccessPolicy:
    """Retrieval-time access control.

    Prefer :func:`evaluate_access` for the canonical truth table. ``decide``
    is a convenience boolean wrapper. ``is_admin`` grants no implicit read.
    """

    def decide(self, ctx: SecurityContext, acl: ResourceAcl) -> bool:
        return evaluate_access(ctx, acl) is AuthorizationDecision.ALLOW

    # Backward-compatible shim for the corpus-level ``allowed_users`` policy
    # exercised by the M0 baseline characterization tests. Superseded by
    # :func:`evaluate_access`; remove once those tests migrate.
    def can_access(self, user_id: str, corpus: Any) -> bool:
        allowed = (getattr(corpus, "access_policy", None) or {}).get("allowed_users")
        if not allowed:
            return True
        return user_id in allowed
