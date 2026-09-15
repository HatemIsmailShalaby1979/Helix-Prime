"""Providers that hand out services bound to the authenticated account.

Each provider takes the account the request guard resolved, never anything from
the request body, so a caller cannot widen its own scope by asking. The store
keeps the memory_stores index current through the request's connection.
"""
from __future__ import annotations

import sqlite3

from helix_codex_app.integration.memory_bridge import AccountMemoryStore
from helix_codex_app.security.accounts import Account


def memory_store_for(
    account: Account,
    *,
    conn: sqlite3.Connection,
    memory_root: str | None = None,
) -> AccountMemoryStore:
    """An AccountMemoryStore bound to this account and its tenant's org store.

    conn is the request's app-database connection. memory_root defaults to the
    configured value; tests pass a temporary directory.
    """
    return AccountMemoryStore(conn=conn, memory_root=memory_root)
