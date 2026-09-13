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
from helix_codex_app.security.accounts import Account
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
