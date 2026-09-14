"""App-local permission catalog and the role-to-permission map.

The nine GM and executive roles in organization/role-catalog.yaml are read
here (read-only, at import time) for the set of privileged role ids; the
file itself is never edited. An account holding one of those ids keeps its
catalog role at the policy seam. An account holding an app role (owner,
manager, employee, contractor, external) has no catalog equivalent and maps
to role_id=None at the seam, which the policy engine denies by construction.
The matrix below mirrors master plan section 5.5. Values are True (granted),
"scoped" (granted only within the caller's own scope), or False (denied).
Unknown permission keys and unknown roles are denied — never allowed.
"""
from __future__ import annotations

import sqlite3

from helix_codex_app.security.accounts import Account
from organization import role_catalog as _role_catalog

PERMISSIONS: tuple[str, ...] = (
    "chat.use",
    "docs.read",
    "docs.write",
    "tasks.use",
    "calendar.use",
    "attendance.punch",
    "notifications.use",
    "memory.propose",
    "memory.review",
    "ops.view",
    "cockpit.view",
    "admin.users",
    "packs.manage",
)

APP_ROLE_IDS: tuple[str, ...] = ("owner", "manager", "employee", "contractor", "external")

_PERMISSION_KEYS = PERMISSIONS

PERMISSION_MATRIX: dict[str, dict[str, bool | str]] = {
    "owner": {key: True for key in _PERMISSION_KEYS},
    "manager": {
        "chat.use": True,
        "docs.read": True,
        "docs.write": True,
        "tasks.use": True,
        "calendar.use": True,
        "attendance.punch": True,
        "notifications.use": True,
        "memory.propose": True,
        "memory.review": True,
        "ops.view": True,
        "cockpit.view": True,
        "admin.users": "scoped",
        "packs.manage": False,
    },
    "employee": {
        "chat.use": True,
        "docs.read": True,
        "docs.write": True,
        "tasks.use": True,
        "calendar.use": True,
        "attendance.punch": True,
        "notifications.use": True,
        "memory.propose": True,
        "memory.review": False,
        "ops.view": False,
        "cockpit.view": False,
        "admin.users": False,
        "packs.manage": False,
    },
    "contractor": {
        "chat.use": True,
        "docs.read": True,
        "docs.write": True,
        "tasks.use": True,
        "calendar.use": True,
        "attendance.punch": True,
        "notifications.use": True,
        "memory.propose": False,
        "memory.review": False,
        "ops.view": False,
        "cockpit.view": False,
        "admin.users": False,
        "packs.manage": False,
    },
    "external": {
        "chat.use": True,
        "docs.read": "scoped",
        "docs.write": False,
        "tasks.use": False,
        "calendar.use": False,
        "attendance.punch": False,
        "notifications.use": True,
        "memory.propose": False,
        "memory.review": False,
        "ops.view": False,
        "cockpit.view": False,
        "admin.users": False,
        "packs.manage": False,
    },
    "catalog": {
        "chat.use": True,
        "docs.read": True,
        "docs.write": True,
        "tasks.use": True,
        "calendar.use": True,
        "attendance.punch": True,
        "notifications.use": True,
        "memory.propose": True,
        "memory.review": True,
        "ops.view": True,
        "cockpit.view": True,
        "admin.users": False,
        "packs.manage": False,
    },
}


def _catalog_role_ids() -> frozenset[str]:
    catalog = _role_catalog.load_role_catalog()
    return frozenset(catalog.get("roles_by_id", {}).keys())


PRIVILEGED_CATALOG_ROLE_IDS: frozenset[str] = _catalog_role_ids()


def permissions_for(account: Account, conn: sqlite3.Connection | None = None) -> frozenset[str]:
    """All permission keys granted to the account, scoped grants included.

    When a database connection is passed, the account's enabled capability
    rows are unioned in, so an admin grant takes effect on the very next
    read. Without a connection the answer is the role matrix alone.
    """
    if account.role_id in PRIVILEGED_CATALOG_ROLE_IDS:
        row = PERMISSION_MATRIX["catalog"]
    else:
        row = PERMISSION_MATRIX.get(account.role_id) or {}
    granted = frozenset(key for key, value in row.items() if value)
    if conn is None:
        return granted
    return granted | capabilities_for(conn, account)


def capabilities_for(conn: sqlite3.Connection, account: Account) -> frozenset[str]:
    """The enabled capability keys granted to the account by an admin."""
    rows = conn.execute(
        "SELECT capability_key FROM account_capabilities" " WHERE account_id = ? AND enabled = 1",
        (account.account_id,),
    ).fetchall()
    return frozenset(row["capability_key"] for row in rows)


def has_permission(
    account: Account,
    key: str,
    conn: sqlite3.Connection | None = None,
) -> bool:
    """True only when the account is granted the key. Deny by default."""
    return key in permissions_for(account, conn)
