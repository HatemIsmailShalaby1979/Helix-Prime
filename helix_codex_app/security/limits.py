"""Per-account quota limits.

Each app role has a default set of limits, seeded into the account_limits
table when an account is created. check_and_consume() is the gate a mutating
service calls before a write: when the account is already at its limit it
raises LimitExceeded and the call never reaches the database. Owner and roles
without numeric quotas are unlimited, marked with a limit value of zero. The
consumed counts live on the account record, in memory, and reset when the
account is reloaded or the process restarts; windowed persistence lands with
the module that owns the quota windows.
"""
from __future__ import annotations

import sqlite3

from helix_codex_app.errors import LimitExceeded
from helix_codex_app.security.accounts import Account

DEFAULT_ROLE_LIMITS: dict[str, dict[str, int]] = {
    "owner": {"storage_mb": 0, "messages_per_day": 0, "records_per_day": 0},
    "manager": {"storage_mb": 5000, "messages_per_day": 5000, "records_per_day": 500},
    "employee": {"storage_mb": 500, "messages_per_day": 2000, "records_per_day": 200},
    "contractor": {"storage_mb": 250, "messages_per_day": 1000, "records_per_day": 100},
    "external": {"storage_mb": 50, "messages_per_day": 200, "records_per_day": 20},
}

FALLBACK_LIMITS = DEFAULT_ROLE_LIMITS["employee"]
UNLIMITED = 0


def defaults_for_role(role_id: str | None) -> dict[str, int]:
    """Return the default limits for a role, or the employee defaults when the
    role is unknown. Unknown roles get the employee floor, never more."""
    if role_id is None:
        return dict(FALLBACK_LIMITS)
    return dict(DEFAULT_ROLE_LIMITS.get(role_id, FALLBACK_LIMITS))


def seed_limits_for_account(conn: sqlite3.Connection, account: Account) -> Account:
    """Write the role's default limits into account_limits and load them onto
    the account record. Returns the same account with limits populated."""
    limits = defaults_for_role(account.role_id)
    for key, value in limits.items():
        conn.execute(
            """
            INSERT OR REPLACE INTO account_limits (account_id, limit_key, limit_value, window)
            VALUES (?, ?, ?, 'day')
            """,
            (account.account_id, key, value),
        )
    conn.commit()
    account.limits.update(limits)
    return account


def load_limits(conn: sqlite3.Connection, account: Account) -> Account:
    """Read the account_limits rows for this account onto the account record.
    A missing row is treated as unlimited, so a limit that was never seeded
    cannot block the account."""
    rows = conn.execute(
        "SELECT limit_key, limit_value FROM account_limits WHERE account_id = ?",
        (account.account_id,),
    ).fetchall()
    for row in rows:
        account.limits[row["limit_key"]] = row["limit_value"]
    return account


def check_and_consume(account: Account, key: str, amount: int = 1) -> None:
    """Charge `amount` against the account's `key` quota, failing closed.

    A limit value of zero means unlimited and never raises. Any other value
    raises LimitExceeded once the account has consumed the whole quota. A key
    with no configured limit is treated as unlimited.
    """
    if amount < 1:
        raise ValueError("check_and_consume: amount must be positive")
    limit_value = account.limits.get(key)
    if limit_value is None or limit_value == UNLIMITED:
        account.consumed[key] = account.consumed.get(key, 0) + amount
        return
    consumed = account.consumed.get(key, 0)
    if consumed + amount > limit_value:
        raise LimitExceeded(
            f"quota {key!r} spent for account {account.account_id}",
            payload={
                "limit_key": key,
                "limit_value": limit_value,
                "consumed": consumed,
                "amount": amount,
                "account_id": account.account_id,
            },
        )
    account.consumed[key] = consumed + amount
