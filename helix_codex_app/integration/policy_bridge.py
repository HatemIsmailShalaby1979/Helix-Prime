"""Bridge an app account to the core policy engine.

This module is the only place that imports the parent security package. An
account reaches the engine with role_id set only when it holds one of the
nine catalog role ids; every app-only role maps to role_id=None and is
denied here, before the engine is consulted, so an employee can never reach
ops. authorize_engine_action forces every request onto the account's own
tenant and client, so no caller can name a foreign scope. Deny by default:
any failure raises PermissionDenied, never allowing.
"""
from __future__ import annotations

import security.policy as _policy
from helix_codex_app.errors import PermissionDenied
from helix_codex_app.security.accounts import (
    DEMO_CLIENT_ID,
    DEMO_ROLE_ID,
    DEMO_TENANT_ID,
    Account,
)
from helix_codex_app.security.permissions import PRIVILEGED_CATALOG_ROLE_IDS
from security.identity import Identity


def to_identity(account: Account) -> Identity:
    """Map an app account to a policy identity.

    role_id is the account's catalog role id when it is one of the nine
    privileged ids, and None otherwise. A None role_id is the fail-closed
    path: the policy engine has never heard of the role, so it denies.
    """
    role_id = account.role_id if account.role_id in PRIVILEGED_CATALOG_ROLE_IDS else None
    return Identity(
        actor=account.account_id,
        actor_type="human",
        tenant_id=account.tenant_id,
        client_id=account.client_id,
        role_id=role_id,
    )


# Which catalog role an app role speaks with when it reaches a governed engine.
# This is not the app permission matrix: it answers "what may this account do
# inside the core". A role with no entry has no engine voice at all, which is
# what keeps an employee out of the ops and cockpit sections.
APP_ROLE_ENGINE_CATALOG_ROLE: dict[str, str] = {
    "owner": "sami",
    "manager": "ops_gm",
}

# The public walkthrough. Its scope is imported from the account layer, which
# declares it once, so the scope that grants the voice and the scope the walkthrough
# account actually resolves to cannot drift apart. "demo" is deliberately NOT a
# key of APP_ROLE_ENGINE_CATALOG_ROLE: that table grants unconditionally, so an
# entry there would hand ops_gm authority to a demo-role account in ANY tenant.
# This voice is granted on an exact tenant+client match, and to nobody else.
DEMO_ENGINE_ROLE: str = "ops_gm"


def demo_voice_allowed(account: Account) -> bool:
    """True only for a demo account inside the one fixed synthetic tenant.

    Both halves must match. A demo-role account in any other tenant, or in the
    demo tenant under a different client, answers False and is refused before
    the engine is consulted.
    """
    return (
        account.role_id == DEMO_ROLE_ID
        and account.tenant_id == DEMO_TENANT_ID
        and account.client_id == DEMO_CLIENT_ID
    )


def to_engine_identity(account: Account) -> Identity:
    """The identity an account uses when it calls a governed engine.

    Separate from to_identity() on purpose. to_identity() answers "what is this
    account in the app" and deliberately yields no catalog role for an app-only
    role — the P1.4 tests pin that. This answers "what may this account do in
    the core": an owner speaks as the executive, a manager as the ops GM, and
    anybody else gets no catalog role and is refused by construction.
    """
    if account.role_id in PRIVILEGED_CATALOG_ROLE_IDS:
        role_id: str | None = account.role_id
    elif account.role_id == DEMO_ROLE_ID:
        role_id = DEMO_ENGINE_ROLE if demo_voice_allowed(account) else None
    else:
        role_id = APP_ROLE_ENGINE_CATALOG_ROLE.get(account.role_id or "")
    return Identity(
        actor=account.account_id,
        actor_type="human",
        tenant_id=account.tenant_id,
        client_id=account.client_id,
        role_id=role_id,
    )


def authorize_engine_call(
    account: Account,
    *,
    capability: str,
    action: str,
    tool: str | None = None,
    owning_role_id: str | None = None,
    requires_approval: bool = False,
) -> _policy.AuthorizationDecision:
    """Authorize one engine call for an account, or raise PermissionDenied.

    The target is always the account's own tenant and client, so a caller cannot
    name a foreign scope. Deny by default: a blank capability, an app role with
    no engine catalog role, or a policy deny all raise.
    """
    if not capability or not capability.strip():
        raise PermissionDenied("policy bridge: capability is required")
    identity = to_engine_identity(account)
    if identity.role_id is None:
        raise PermissionDenied(
            "no catalog role: the policy engine denies by construction",
            payload={"account_id": account.account_id, "role_id": account.role_id},
        )
    scoped = _policy.AuthorizationRequest(
        identity=identity,
        capability=capability,
        tool=tool,
        action=action,
        requires_approval=requires_approval,
        owning_role_id=owning_role_id,
        target_tenant_id=account.tenant_id,
        target_client_id=account.client_id,
    )
    decision = _policy.authorize(scoped)
    if not decision.allowed:
        raise PermissionDenied(
            f"policy denied: {decision.reason}",
            payload={
                "account_id": account.account_id,
                "capability": capability,
                "code": decision.code,
            },
        )
    return decision


def authorize_engine_action(
    account: Account, request: _policy.AuthorizationRequest
) -> _policy.AuthorizationDecision:
    """Authorize an engine action on behalf of the account, or raise.

    The request's identity and scope are rebuilt from the account: the
    caller supplies capability, tool, action, and owning_role_id only, and
    the target is always the account's own tenant and client. Deny by
    default — any invalid input, non-catalog role, or policy deny raises
    PermissionDenied.
    """
    if not isinstance(request, _policy.AuthorizationRequest):
        raise PermissionDenied("policy bridge: invalid authorization request")
    identity = to_identity(account)
    if identity.role_id is None:
        raise PermissionDenied(
            "no catalog role: policy engine denies by construction",
            payload={"account_id": account.account_id, "role_id": account.role_id},
        )
    scoped = _policy.AuthorizationRequest(
        identity=identity,
        capability=request.capability,
        tool=request.tool,
        action=request.action,
        requires_approval=request.requires_approval,
        owning_role_id=request.owning_role_id,
        target_tenant_id=account.tenant_id,
        target_client_id=account.client_id,
    )
    decision = _policy.authorize(scoped)
    if not decision.allowed:
        raise PermissionDenied(
            f"policy denied: {decision.reason}",
            payload={
                "account_id": account.account_id,
                "capability": scoped.capability,
                "code": decision.code,
            },
        )
    return decision
