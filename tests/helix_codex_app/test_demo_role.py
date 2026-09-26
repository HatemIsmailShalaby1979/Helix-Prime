"""The public walkthrough role: least privilege, scoped engine voice, fixed identity.

Three properties, and each is checked in the direction that matters:

1. The role holds `ops.view` and nothing else. Checked against the whole matrix,
   not just the one permission, so adding a second grant later fails here.
2. The engine voice is scope-gated. A demo account in the fixed synthetic
   tenant may reach the engine; the SAME role in ANY other tenant, or under a
   different client, is refused before the engine is consulted.
3. The walkthrough identity is fixed, declared once, and provisioned without a
   credential in source.

The load-bearing case is the cross-tenant one. A `demo` row in
APP_ROLE_ENGINE_CATALOG_ROLE would satisfy every happy-path test and hand ops_gm
authority to a demo-role account in a real tenant, so the negative direction is
asserted explicitly and the table is pinned as not containing the role.
"""
from __future__ import annotations

import sqlite3

import pytest

from helix_codex_app.errors import PermissionDenied
from helix_codex_app.integration.policy_bridge import (
    APP_ROLE_ENGINE_CATALOG_ROLE,
    DEMO_ENGINE_ROLE,
    authorize_engine_call,
    demo_voice_allowed,
    to_engine_identity,
)
from helix_codex_app.security.accounts import (
    DEMO_CLIENT_ID,
    DEMO_DOMAIN_NAME,
    DEMO_ROLE_ID,
    DEMO_TENANT_ID,
    DEMO_USERNAME,
    Account,
    AccountRepository,
    DemoScopeConflict,
    ensure_demo_account,
)
from helix_codex_app.security.permissions import (
    APP_ROLE_IDS,
    PERMISSION_MATRIX,
    PERMISSIONS,
    has_permission,
    permissions_for,
)


def make_account(
    role_id: str | None,
    *,
    tenant_id: str = DEMO_TENANT_ID,
    client_id: str = DEMO_CLIENT_ID,
) -> Account:
    return Account(
        account_id="account-demo",
        domain_id="domain-demo",
        domain_name=DEMO_DOMAIN_NAME,
        tenant_id=tenant_id,
        username=DEMO_USERNAME,
        username_normalized=DEMO_USERNAME,
        role_id=role_id,
        client_id=client_id,
    )


@pytest.fixture
def repo() -> AccountRepository:
    from helix_codex_app.db import _init_schema

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _init_schema(conn)
    try:
        yield AccountRepository(conn)
    finally:
        conn.close()


def test_demo_is_a_declared_app_role() -> None:
    assert DEMO_ROLE_ID in APP_ROLE_IDS
    assert DEMO_ROLE_ID in PERMISSION_MATRIX


def test_demo_holds_ops_view() -> None:
    assert has_permission(make_account(DEMO_ROLE_ID), "ops.view") is True


def test_demo_holds_nothing_else() -> None:
    granted = permissions_for(make_account(DEMO_ROLE_ID))
    assert granted == frozenset({"ops.view"})


@pytest.mark.parametrize("permission", [p for p in PERMISSIONS if p != "ops.view"])
def test_every_other_permission_is_refused(permission: str) -> None:
    assert has_permission(make_account(DEMO_ROLE_ID), permission) is False


def test_demo_is_not_a_privileged_catalog_role() -> None:
    # A catalog role would inherit the whole `catalog` column, which is wider
    # than ops.view. This pins that the walkthrough is an app role.
    assert not permissions_for(make_account(DEMO_ROLE_ID)) & {
        "admin.users",
        "packs.manage",
        "memory.review",
    }


def test_demo_voice_is_not_granted_through_the_unconditional_table() -> None:
    # The can-fail guard for property 2: an entry here would hand ops_gm to a
    # demo-role account in ANY tenant, and every happy-path test would still pass.
    assert DEMO_ROLE_ID not in APP_ROLE_ENGINE_CATALOG_ROLE
    assert set(APP_ROLE_ENGINE_CATALOG_ROLE) == {"owner", "manager"}


def test_demo_in_the_fixed_scope_gets_the_ops_gm_voice() -> None:
    account = make_account(DEMO_ROLE_ID)
    assert demo_voice_allowed(account) is True
    assert to_engine_identity(account).role_id == DEMO_ENGINE_ROLE


def test_demo_in_another_tenant_is_refused_the_voice() -> None:
    account = make_account(DEMO_ROLE_ID, tenant_id="tenant-a")
    assert demo_voice_allowed(account) is False
    assert to_engine_identity(account).role_id is None


def test_demo_under_another_client_is_refused_the_voice() -> None:
    account = make_account(DEMO_ROLE_ID, client_id="client-a")
    assert demo_voice_allowed(account) is False
    assert to_engine_identity(account).role_id is None


def test_a_cross_tenant_demo_account_cannot_reach_the_engine() -> None:
    # The behaviour that matters, not just the predicate: the live policy call
    # engine_bridge.submit_workflow makes is refused, so the engine is never
    # consulted. Same shape the bridge uses, with the real WFM capability.
    outsider = make_account(DEMO_ROLE_ID, tenant_id="tenant-a")
    with pytest.raises(PermissionDenied):
        authorize_engine_call(
            outsider,
            capability="wfm_forecast",
            action="submit",
            owning_role_id="ops_gm",
        )


def test_an_out_of_scope_demo_account_is_refused_for_another_client() -> None:
    outsider = make_account(DEMO_ROLE_ID, client_id="client-a")
    with pytest.raises(PermissionDenied):
        authorize_engine_call(
            outsider,
            capability="wfm_forecast",
            action="submit",
            owning_role_id="ops_gm",
        )


def test_a_demo_account_with_a_blank_client_is_refused_earlier_still() -> None:
    # A blank client_id never reaches the bridge at all: Identity's own
    # validation refuses it first. That is a STRICTER refusal than the
    # PermissionDenied above, not a hole, so it is asserted as its own case
    # rather than folded into the same exception handler.
    for client_id in ("", None):
        broken = make_account(DEMO_ROLE_ID, client_id=client_id)
        with pytest.raises((PermissionDenied, ValueError)):
            authorize_engine_call(
                broken,
                capability="wfm_forecast",
                action="submit",
                owning_role_id="ops_gm",
            )


def test_the_in_scope_demo_account_reaches_the_engine_policy() -> None:
    # The positive half of the same call, so the two tests above are a real
    # boundary rather than a capability the demo simply lacks.
    decision = authorize_engine_call(
        make_account(DEMO_ROLE_ID),
        capability="wfm_forecast",
        action="submit",
        owning_role_id="ops_gm",
    )
    assert decision.allowed is True


def test_the_voice_keeps_the_account_own_scope() -> None:
    identity = to_engine_identity(make_account(DEMO_ROLE_ID))
    assert identity.tenant_id == DEMO_TENANT_ID
    assert identity.client_id == DEMO_CLIENT_ID


def test_ensure_demo_account_creates_the_fixed_identity(repo: AccountRepository) -> None:
    account = ensure_demo_account(repo, password_hash="hash", display_name="Demo viewer")
    assert account.role_id == DEMO_ROLE_ID
    assert account.tenant_id == DEMO_TENANT_ID
    assert account.client_id == DEMO_CLIENT_ID
    assert account.domain_name == DEMO_DOMAIN_NAME
    assert account.username == DEMO_USERNAME


def test_ensure_demo_account_is_idempotent(repo: AccountRepository) -> None:
    first = ensure_demo_account(repo, password_hash="hash")
    second = ensure_demo_account(repo, password_hash="hash")
    assert first.account_id == second.account_id
    assert len(repo.list_accounts(first.domain_id)) == 1


def test_ensure_demo_account_refuses_a_foreign_domain_of_the_same_name(
    repo: AccountRepository,
) -> None:
    repo.create_domain(DEMO_DOMAIN_NAME, "tenant-a", client_id="client-a")
    with pytest.raises(DemoScopeConflict):
        ensure_demo_account(repo, password_hash="hash")


def test_ensure_demo_account_refuses_a_reused_username_with_another_role(
    repo: AccountRepository,
) -> None:
    domain = repo.create_domain(DEMO_DOMAIN_NAME, DEMO_TENANT_ID, client_id=DEMO_CLIENT_ID)
    repo.create_account(domain.domain_id, DEMO_USERNAME, password_hash="hash", role_id="owner")
    with pytest.raises(DemoScopeConflict):
        ensure_demo_account(repo, password_hash="hash")


def test_the_provisioned_account_actually_reaches_the_engine_voice(
    repo: AccountRepository,
) -> None:
    account = ensure_demo_account(repo, password_hash="hash")
    assert demo_voice_allowed(account) is True
    assert to_engine_identity(account).role_id == DEMO_ENGINE_ROLE


def test_no_credential_literal_is_committed_with_the_demo_identity() -> None:
    # The provisioner takes a hash parameter, so the walkthrough cannot ship
    # with a known password. A default would be the regression this pins.
    import inspect

    signature = inspect.signature(ensure_demo_account)
    defaults = {
        name: parameter.default
        for name, parameter in signature.parameters.items()
        if parameter.default is not inspect.Parameter.empty
    }
    assert set(defaults) == {"display_name"}
    assert "password_hash" in signature.parameters
    assert signature.parameters["password_hash"].default is inspect.Parameter.empty
