"""
Segregation of duties — the single implementation every layer delegates to.

The platform answers "may this actor approve that work?" in five places, at five
different layers: the C1 action contract (``contracts/task.py``), the C2 workflow
engine (``control_plane/engine.py``), the governed workflow manager
(``control_plane/governance.py``), the C3 capability authorizer
(``security/policy.py``), and the pilot approval loop (``pilot/approval.py``).
Each carried its own copy of the rule, so the copies could drift apart without
anything failing.

This module declares the rule once. It imports nothing from the repository, so
every layer above it can import it without a cycle and the predicates stay pure.

Four facts the rule is built from:

``self_approval``
    An actor may never approve their own work.
``same_role``
    An approver holding the role that owns the work may not approve it.
``unauthorized_reviewer``
    An approver must be named as a reviewer of the owning role — by that role's
    ``segregation_of_duties.must_be_reviewed_by`` list or by the catalog's
    ``universal_approvers`` — or must name the owning role in their own
    ``segregation_of_duties.can_review``.
``unauthorized_peer``
    A role may act on a capability it owns, on one owned by a role in its
    ``allowed_peer_calls``, or on any as a universal approver.

**Verdicts belong to the callers, and this module does not change them.**
Unifying the predicates is not the same as unifying the policies. The governed
workflow manager has never forbidden same-role approval, so it passes
``enforce_same_role=False``; the pilot loop keeps its own implementation because
``pilot/`` is a frozen deployed artifact, and ``tests/test_segregation_of_duties.py``
pins its verdicts to these predicates instead. Every caller keeps its own
exception type, message and scope — nothing is silently widened or narrowed.
"""
from __future__ import annotations

from typing import Any, Iterable, List, Mapping, Optional, Sequence

#: The approver is the actor whose work is being approved.
SOD_SELF_APPROVAL = "self_approval"

#: The approver holds the role that owns the work.
SOD_SAME_ROLE = "same_role"

#: The approver is not authorised to review the owning role.
SOD_UNAUTHORIZED_REVIEWER = "unauthorized_reviewer"

#: The role may not act on a capability owned by the owning role.
SOD_UNAUTHORIZED_PEER = "unauthorized_peer"

#: Every violation code this module can return, in the order they are tested.
SOD_VIOLATIONS = (
    SOD_SELF_APPROVAL,
    SOD_SAME_ROLE,
    SOD_UNAUTHORIZED_REVIEWER,
    SOD_UNAUTHORIZED_PEER,
)


def self_approval_violation(actor: str, approver_actor: str) -> bool:
    """True when the approver is the actor whose own work is being approved."""
    return approver_actor == actor


def same_role_violation(owning_role_id: str, approver_role_id: str) -> bool:
    """True when the approver holds the role that owns the work."""
    return approver_role_id == owning_role_id


def approval_violation(
    actor: str,
    approver_actor: str,
    owning_role_id: str,
    approver_role_id: str,
    *,
    enforce_same_role: bool = True,
) -> Optional[str]:
    """
    Return the approval-time SOD violation code, or ``None`` when the pair is clean.

    ``enforce_same_role`` records a caller's existing policy rather than hiding a
    default: ``control_plane/governance.py`` passes ``False`` because it has never
    forbidden same-role approval, and that divergence is pinned by test.
    """
    if self_approval_violation(actor, approver_actor):
        return SOD_SELF_APPROVAL
    if enforce_same_role and same_role_violation(owning_role_id, approver_role_id):
        return SOD_SAME_ROLE
    return None


def is_universal_approver(universal_approvers: Iterable[str], role_id: str) -> bool:
    """True when the catalog names this role a universal approver."""
    return role_id in set(universal_approvers)


def sod_entries(roles_by_id: Mapping[str, Any], role_id: str) -> Mapping[str, Any]:
    """Return a role's ``segregation_of_duties`` mapping, or an empty one."""
    role = roles_by_id.get(role_id) or {}
    if not isinstance(role, Mapping):
        return {}
    entries = role.get("segregation_of_duties") or {}
    return entries if isinstance(entries, Mapping) else {}


def declared_reviewers(roles_by_id: Mapping[str, Any], owning_role_id: str) -> List[str]:
    """The roles the owning role declares must review it."""
    return list(sod_entries(roles_by_id, owning_role_id).get("must_be_reviewed_by") or [])


def declared_review_scope(roles_by_id: Mapping[str, Any], approver_role_id: str) -> List[str]:
    """The owning roles the approver declares it may review."""
    return list(sod_entries(roles_by_id, approver_role_id).get("can_review") or [])


def declared_peer_calls(roles_by_id: Mapping[str, Any], actor_role_id: str) -> List[str]:
    """The roles whose capabilities this role declares it may act on."""
    role = roles_by_id.get(actor_role_id) or {}
    if not isinstance(role, Mapping):
        return []
    return list(role.get("allowed_peer_calls") or [])


def reviewer_authority_violation(
    roles_by_id: Mapping[str, Any],
    universal_approvers: Iterable[str],
    owning_role_id: str,
    approver_role_id: str,
) -> bool:
    """
    True when the approver is not authorised to review the owning role.

    Authorised means: named in the owning role's ``must_be_reviewed_by``, named a
    universal approver, or the owning role appears in the approver's
    ``can_review``. The first list is read as an allow-list, which is how every
    caller has always read it.
    """
    allowed = set(declared_reviewers(roles_by_id, owning_role_id))
    allowed |= set(universal_approvers)
    if approver_role_id in allowed:
        return False
    return owning_role_id not in declared_review_scope(roles_by_id, approver_role_id)


def peer_authority_violation(
    roles_by_id: Mapping[str, Any],
    universal_approvers: Iterable[str],
    actor_role_id: str,
    owner_role_id: str,
) -> bool:
    """True when a role may not act on a capability owned by ``owner_role_id``."""
    if actor_role_id == owner_role_id:
        return False
    if owner_role_id in declared_peer_calls(roles_by_id, actor_role_id):
        return False
    return not is_universal_approver(universal_approvers, actor_role_id)


def approval_sod_verdict(
    *,
    roles_by_id: Mapping[str, Any],
    universal_approvers: Sequence[str],
    actor: str,
    approver_actor: str,
    owning_role_id: str,
    approver_role_id: str,
    enforce_same_role: bool = True,
) -> Optional[str]:
    """
    The whole approval decision as one call: identity first, then authority.

    Callers that only need one half should call the specific predicate, so their
    scope stays readable and their verdict stays theirs.
    """
    violation = approval_violation(
        actor,
        approver_actor,
        owning_role_id,
        approver_role_id,
        enforce_same_role=enforce_same_role,
    )
    if violation is not None:
        return violation
    if reviewer_authority_violation(
        roles_by_id, universal_approvers, owning_role_id, approver_role_id
    ):
        return SOD_UNAUTHORIZED_REVIEWER
    return None
