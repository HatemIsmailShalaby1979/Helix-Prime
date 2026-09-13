"""Repository tests for helix_codex_app/security/accounts.py.

Each test uses a throwaway database under tmp_path so data never touches the
real app.db. Connections are opened and closed by the helpers here, because
Windows keeps a file lock on an open SQLite handle and leaked handles break
teardown.
"""
from __future__ import annotations

import pytest

from helix_codex_app import db
from helix_codex_app.errors import LimitExceeded
from helix_codex_app.security import passwords
from helix_codex_app.security.accounts import (
    AccountRepository,
    DuplicateDomain,
    DuplicateUsername,
    NoSuchAccount,
    NoSuchDomain,
)
from helix_codex_app.security.limits import (
    check_and_consume,
    defaults_for_role,
    seed_limits_for_account,
)


@pytest.fixture()
def repo(tmp_path):
    conn = db.connect(db_path=str(tmp_path / "app.db"))
    db._init_schema(conn)
    repository = AccountRepository(conn)
    yield repository
    db.close(conn)


def test_create_domain_round_trip(repo) -> None:
    domain = repo.create_domain("scoach.academy", tenant_id="tenant-academy-1")
    found = repo.get_domain_by_name("scoach.academy")
    assert found is not None
    assert found.domain_id == domain.domain_id
    assert found.tenant_id == "tenant-academy-1"
    assert found.status == "active"


def test_create_domain_duplicate_rejected(repo) -> None:
    repo.create_domain("scoach.academy", tenant_id="tenant-academy-1")
    with pytest.raises(DuplicateDomain):
        repo.create_domain("scoach.academy", tenant_id="tenant-other")


def test_account_round_trip_scoped_to_domain(repo) -> None:
    domain = repo.create_domain("scoach.academy", tenant_id="tenant-academy-1")
    stored = passwords.hash_password("s3cret")
    account = repo.create_account(
        domain.domain_id,
        "Amira",
        password_hash=stored,
        display_name="Amira Khan",
        role_id="manager",
    )
    found = repo.get_account_by_login("scoach.academy", "amira")
    assert found is not None
    assert found.account_id == account.account_id
    assert found.tenant_id == "tenant-academy-1"
    assert found.domain_name == "scoach.academy"
    assert found.username == "Amira"
    assert found.username_normalized == "amira"
    assert found.role_id == "manager"
    assert passwords.verify_password("s3cret", found.password_hash)


def test_duplicate_username_same_domain_rejected(repo) -> None:
    domain = repo.create_domain("scoach.academy", tenant_id="tenant-academy-1")
    repo.create_account(domain.domain_id, "amira", password_hash=passwords.hash_password("x"))
    with pytest.raises(DuplicateUsername):
        repo.create_account(domain.domain_id, "Amira", password_hash=passwords.hash_password("y"))


def test_same_username_other_domain_allowed(repo) -> None:
    domain_a = repo.create_domain("a.academy", tenant_id="tenant-a")
    domain_b = repo.create_domain("b.academy", tenant_id="tenant-b")
    account_a = repo.create_account(
        domain_a.domain_id, "amira", password_hash=passwords.hash_password("x")
    )
    account_b = repo.create_account(
        domain_b.domain_id, "amira", password_hash=passwords.hash_password("y")
    )
    assert account_a.account_id != account_b.account_id
    assert account_a.tenant_id == "tenant-a"
    assert account_b.tenant_id == "tenant-b"
    only_a = repo.get_account_by_login("a.academy", "amira")
    only_b = repo.get_account_by_login("b.academy", "amira")
    assert only_a.account_id == account_a.account_id
    assert only_b.account_id == account_b.account_id


def test_login_with_unknown_domain_finds_nothing(repo) -> None:
    domain = repo.create_domain("scoach.academy", tenant_id="tenant-academy-1")
    repo.create_account(domain.domain_id, "amira", password_hash=passwords.hash_password("x"))
    assert repo.get_account_by_login("other.academy", "amira") is None


def test_get_account_by_unknown_id_is_none(repo) -> None:
    assert repo.get_account_by_id("account-does-not-exist") is None


def test_list_accounts_scoped_to_domain(repo) -> None:
    domain = repo.create_domain("scoach.academy", tenant_id="tenant-academy-1")
    repo.create_account(domain.domain_id, "amira", password_hash=passwords.hash_password("x"))
    repo.create_account(domain.domain_id, "omar", password_hash=passwords.hash_password("x"))
    assert {a.username_normalized for a in repo.list_accounts(domain.domain_id)} == {
        "amira",
        "omar",
    }


def test_update_account_fields(repo) -> None:
    domain = repo.create_domain("scoach.academy", tenant_id="tenant-academy-1")
    account = repo.create_account(
        domain.domain_id, "amira", password_hash=passwords.hash_password("x")
    )
    updated = repo.update_account(
        account.account_id, display_name="Amira Updated", role_id="employee"
    )
    assert updated.display_name == "Amira Updated"
    assert updated.role_id == "employee"


def test_update_account_nothing_raises(repo) -> None:
    domain = repo.create_domain("scoach.academy", tenant_id="tenant-academy-1")
    account = repo.create_account(
        domain.domain_id, "amira", password_hash=passwords.hash_password("x")
    )
    with pytest.raises(ValueError):
        repo.update_account(account.account_id)


def test_set_status(repo) -> None:
    domain = repo.create_domain("scoach.academy", tenant_id="tenant-academy-1")
    account = repo.create_account(
        domain.domain_id, "amira", password_hash=passwords.hash_password("x")
    )
    disabled = repo.set_status(account.account_id, "disabled")
    assert disabled.status == "disabled"


def test_failed_attempts_and_reset(repo) -> None:
    domain = repo.create_domain("scoach.academy", tenant_id="tenant-academy-1")
    account = repo.create_account(
        domain.domain_id, "amira", password_hash=passwords.hash_password("x")
    )
    bumped = repo.record_failed_attempt(account.account_id)
    assert bumped.failed_attempts == 1
    cleared = repo.reset_failed_attempts(account.account_id)
    assert cleared.failed_attempts == 0
    assert cleared.locked_until is None


def test_lock_account_sets_locked_until(repo) -> None:
    domain = repo.create_domain("scoach.academy", tenant_id="tenant-academy-1")
    account = repo.create_account(
        domain.domain_id, "amira", password_hash=passwords.hash_password("x")
    )
    locked = repo.lock_account(account.account_id)
    assert locked.status == "locked"
    assert locked.locked_until is not None


def test_org_units(repo) -> None:
    domain = repo.create_domain("scoach.academy", tenant_id="tenant-academy-1")
    repo.create_org_unit(domain.domain_id, "Coaches")
    repo.create_org_unit(domain.domain_id, "Parents")
    units = repo.list_org_units(domain.domain_id)
    assert {u.name for u in units} == {"Coaches", "Parents"}
    assert {u.path for u in units} == {"/Coaches", "/Parents"}


def test_no_such_domain_on_account_creation(repo) -> None:
    with pytest.raises(NoSuchDomain):
        repo.create_account("domain-missing", "amira", password_hash=passwords.hash_password("x"))


def test_no_such_account_on_update(repo) -> None:
    with pytest.raises(NoSuchAccount):
        repo.update_account("account-missing", display_name="nobody")


def test_limits_seeded_for_role(repo) -> None:
    domain = repo.create_domain("scoach.academy", tenant_id="tenant-academy-1")
    account = repo.create_account(
        domain.domain_id,
        "amira",
        password_hash=passwords.hash_password("x"),
        role_id="employee",
    )
    seeded = seed_limits_for_account(repo.conn, account)
    assert seeded.limits["storage_mb"] == 500
    assert seeded.limits["messages_per_day"] == 2000


def test_limit_exceeded_raises(repo) -> None:
    domain = repo.create_domain("scoach.academy", tenant_id="tenant-academy-1")
    account = repo.create_account(
        domain.domain_id,
        "amira",
        password_hash=passwords.hash_password("x"),
        role_id="employee",
    )
    seed_limits_for_account(repo.conn, account)
    check_and_consume(account, "messages_per_day", 1999)
    check_and_consume(account, "messages_per_day", 1)
    with pytest.raises(LimitExceeded):
        check_and_consume(account, "messages_per_day", 1)


def test_owner_limits_unlimited(repo) -> None:
    domain = repo.create_domain("scoach.academy", tenant_id="tenant-academy-1")
    account = repo.create_account(
        domain.domain_id,
        "owner1",
        password_hash=passwords.hash_password("x"),
        role_id="owner",
    )
    seed_limits_for_account(repo.conn, account)
    check_and_consume(account, "storage_mb", 10**12)
    check_and_consume(account, "messages_per_day", 10**12)


def test_defaults_for_role_fallback(repo) -> None:
    assert defaults_for_role("employee")["messages_per_day"] == 2000
    assert (
        defaults_for_role("manager")["messages_per_day"]
        > defaults_for_role("employee")["messages_per_day"]
    )
    assert defaults_for_role("owner")["storage_mb"] == 0
    assert defaults_for_role("unknown_role")["messages_per_day"] == 2000
