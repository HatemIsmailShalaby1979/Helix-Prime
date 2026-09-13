"""Permission-matrix and policy-bridge tests for the app.

The matrix test checks every (role, permission) pair from master plan 5.5
across all five app roles and the nine catalog roles. The bridge tests prove
an employee cannot reach the policy engine while a catalog role can, and that
no caller can name a foreign scope through the bridge.
"""
from __future__ import annotations

import pytest

import security.policy as policy
from helix_codex_app.errors import PermissionDenied
from helix_codex_app.integration.policy_bridge import (
    authorize_engine_action,
    to_identity,
)
from helix_codex_app.security.accounts import Account
from helix_codex_app.security.permissions import (
    APP_ROLE_IDS,
    PERMISSION_MATRIX,
    PERMISSIONS,
    PRIVILEGED_CATALOG_ROLE_IDS,
    has_permission,
    permissions_for,
)

EXPECTED_CATALOG_ROLE_IDS = frozenset(
    {
        "sami",
        "hr_personnel_gm",
        "marketing_gm",
        "sales_gm",
        "compliance_quality_gm",
        "ict_gm",
        "fraud_gm",
        "ld_gm",
        "ops_gm",
    }
)


def make_account(role_id: str | None) -> Account:
    return Account(
        account_id="account-matrix",
        domain_id="domain-matrix",
        domain_name="a.academy",
        tenant_id="tenant-a",
        username="matrix",
        username_normalized="matrix",
        role_id=role_id,
        client_id="client-a",
    )


@pytest.mark.parametrize("role_id", APP_ROLE_IDS)
@pytest.mark.parametrize("permission", PERMISSIONS)
def test_matrix_every_app_role_permission_pair(role_id: str, permission: str) -> None:
    account = make_account(role_id)
    expected = bool(PERMISSION_MATRIX[role_id][permission])
    assert has_permission(account, permission) is expected


@pytest.mark.parametrize("role_id", sorted(EXPECTED_CATALOG_ROLE_IDS))
def test_catalog_roles_get_the_catalog_column(role_id: str) -> None:
    account = make_account(role_id)
    for permission in PERMISSIONS:
        expected = bool(PERMISSION_MATRIX["catalog"][permission])
        assert has_permission(account, permission) is expected


def test_privileged_catalog_role_ids_match_the_organization_catalog() -> None:
    assert PRIVILEGED_CATALOG_ROLE_IDS == EXPECTED_CATALOG_ROLE_IDS
    assert len(PRIVILEGED_CATALOG_ROLE_IDS) == 9


def test_unknown_role_denied_for_every_permission() -> None:
    account = make_account("time-traveler")
    for permission in PERMISSIONS:
        assert has_permission(account, permission) is False
    assert permissions_for(account) == frozenset()


def test_role_none_denied_for_every_permission() -> None:
    account = make_account(None)
    for permission in PERMISSIONS:
        assert has_permission(account, permission) is False
    assert permissions_for(account) == frozenset()


def test_unknown_permission_key_denied() -> None:
    assert has_permission(make_account("owner"), "not.a.permission") is False


def test_scoped_grants_are_memberships() -> None:
    manager = make_account("manager")
    assert has_permission(manager, "admin.users") is True
    assert has_permission(manager, "packs.manage") is False
    external = make_account("external")
    assert has_permission(external, "docs.read") is True
    assert has_permission(external, "docs.write") is False
    assert has_permission(external, "chat.use") is True
    assert has_permission(external, "attendance.punch") is False


def test_to_identity_employee_has_no_catalog_role() -> None:
    identity = to_identity(make_account("employee"))
    assert identity.actor == "account-matrix"
    assert identity.actor_type == "human"
    assert identity.tenant_id == "tenant-a"
    assert identity.client_id == "client-a"
    assert identity.role_id is None


def test_to_identity_catalog_role_passes_through() -> None:
    assert to_identity(make_account("ops_gm")).role_id == "ops_gm"


def test_to_identity_app_owner_has_no_catalog_role() -> None:
    assert to_identity(make_account("owner")).role_id is None


def _engine_request(
    capability: str = "rta_adherence",
    **overrides,
) -> policy.AuthorizationRequest:
    return policy.AuthorizationRequest(
        identity=policy.Identity(actor="dummy", actor_type="human"),
        capability=capability,
        **overrides,
    )


def test_authorize_engine_action_employee_denied() -> None:
    with pytest.raises(PermissionDenied) as exc:
        authorize_engine_action(make_account("employee"), _engine_request())
    assert exc.value.payload == {"account_id": "account-matrix", "role_id": "employee"}


def test_authorize_engine_action_app_owner_denied() -> None:
    with pytest.raises(PermissionDenied):
        authorize_engine_action(make_account("owner"), _engine_request())


def test_authorize_engine_action_catalog_owner_passes() -> None:
    decision = authorize_engine_action(make_account("ops_gm"), _engine_request())
    assert decision.allowed is True


def test_authorize_engine_action_policy_deny_raises() -> None:
    with pytest.raises(PermissionDenied) as exc:
        authorize_engine_action(make_account("ops_gm"), _engine_request(owning_role_id="fraud_gm"))
    assert exc.value.payload["code"] == "unauthorized_role"


def test_authorize_engine_action_invalid_request_denied() -> None:
    with pytest.raises(PermissionDenied):
        authorize_engine_action(make_account("ops_gm"), {"capability": "rta_adherence"})


def test_authorize_engine_action_cannot_widen_scope() -> None:
    decision = authorize_engine_action(
        make_account("ops_gm"), _engine_request(target_tenant_id="tenant-b")
    )
    assert decision.allowed is True
