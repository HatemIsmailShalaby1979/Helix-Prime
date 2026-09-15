"""Per-account governed memory stores, plus one shared org store per tenant.

Every account gets its own governed memory store, and each tenant gets one org
store for knowledge the whole company shares. A store path is computed from the
authenticated account alone. There is no parameter through which a caller could
name a foreign account, so isolation holds by construction rather than by a
filter that someone could forget to apply.

This module is the only place in the app that imports the parent memory
package. The JSONL ledger stays the source of truth; the memory_stores table is
a projection, refreshed on every write, so the index can never drift ahead of
the ledger.
"""
from __future__ import annotations

import pathlib
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from helix_codex_app import db
from helix_codex_app.config import get_app_settings
from helix_codex_app.security.accounts import Account
from memory.governed_memory import GovernedMemory, MemoryRecord

ORG_KEY = "_org"
STORE_FILENAME = "governed_memory.jsonl"
ACCOUNT_STORE_KIND = "account"
ORG_STORE_KIND = "org"
DEFAULT_CLASSIFICATION = "client_confidential"
DEFAULT_DATA_MODE = "simulated_realistic"
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_component(value: str, *, field: str) -> str:
    """A path component that cannot escape its own directory.

    Rejects separators, absolute paths, and anything containing "..", so a value
    that arrived from a form can never address another tenant's store.
    """
    if not value or not _SAFE_COMPONENT.match(value) or ".." in value:
        raise ValueError(f"memory store: unsafe {field} {value!r}")
    return value


def resolve_store_path(*, memory_root: str, domain_id: str, account_id: str | None) -> str:
    """Compute a store path from server-side values.

    The key is the server-generated domain id, never the caller-supplied
    tenant_id: two domains that happen to be given the same tenant_id still get
    separate stores, so a store cannot be shared by accident or on purpose.
    account_id None means the domain's shared org store. This is the single
    place a path is built; every caller goes through it.
    """
    domain = safe_component(domain_id, field="domain_id")
    key = safe_component(account_id, field="account_id") if account_id else ORG_KEY
    return str(pathlib.Path(memory_root) / domain / key / STORE_FILENAME)


class AccountMemoryStore:
    """Governed memory bound to one account, plus that tenant's org store."""

    def __init__(
        self,
        *,
        conn: sqlite3.Connection | None = None,
        memory_root: str | None = None,
    ) -> None:
        self._conn = conn
        self._root = memory_root or get_app_settings().memory_root
        self._stores: dict[str, GovernedMemory] = {}

    # ------------------------------------------------------------ resolution
    def resolve_store(self, account: Account) -> str:
        """The account's own store path. Derived from the account, never a request."""
        if not account.domain_id or not account.account_id:
            raise ValueError("memory store: domain_id and account_id are required")
        return resolve_store_path(
            memory_root=self._root,
            domain_id=account.domain_id,
            account_id=account.account_id,
        )

    def resolve_org_store(self, account: Account) -> str:
        """The domain's shared org store path."""
        if not account.domain_id:
            raise ValueError("memory store: domain_id is required")
        return resolve_store_path(
            memory_root=self._root,
            domain_id=account.domain_id,
            account_id=None,
        )

    def store_for(self, account: Account) -> GovernedMemory:
        """Open (and index) the account's own store."""
        return self._open(self.resolve_store(account), kind=ACCOUNT_STORE_KIND, account=account)

    def org_store_for(self, account: Account) -> GovernedMemory:
        """Open (and index) the tenant's shared org store."""
        return self._open(self.resolve_org_store(account), kind=ORG_STORE_KIND, account=account)

    def _open(self, path: str, *, kind: str, account: Account) -> GovernedMemory:
        store = self._stores.get(path)
        if store is None:
            pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
            store = GovernedMemory(path=path)
            self._stores[path] = store
        self._index(account=account, path=path, kind=kind, store=store)
        return store

    def _index(self, *, account: Account, path: str, kind: str, store: GovernedMemory) -> None:
        """Keep the memory_stores projection current. A no-op without a connection."""
        if self._conn is None:
            return
        store_id = db.register_store(
            self._conn,
            tenant_id=account.tenant_id,
            account_id=account.account_id if kind == ACCOUNT_STORE_KIND else None,
            kind=kind,
            path=path,
        )
        db.touch_store(
            self._conn,
            store_id=store_id,
            record_count=store.record_count(),
            chain_head=store.chain_head(),
        )

    # ---------------------------------------------------------------- writes
    def record(
        self,
        account: Account,
        *,
        kind: str,
        nature: str,
        body: Mapping[str, Any] | None = None,
        evidence_refs: Sequence[str] | None = None,
        source: str = "app_action",
        classification: str = DEFAULT_CLASSIFICATION,
        correlation_id: str = "",
        data_mode: str = DEFAULT_DATA_MODE,
        confidence: float = 1.0,
    ) -> MemoryRecord:
        """Append one record to the account's own store."""
        return self._append(
            account=account,
            path=self.resolve_store(account),
            kind=kind,
            nature=nature,
            body=body,
            evidence_refs=evidence_refs,
            source=source,
            classification=classification,
            correlation_id=correlation_id,
            data_mode=data_mode,
            confidence=confidence,
            basis="account_memory",
            store_kind=ACCOUNT_STORE_KIND,
        )

    def record_org(
        self,
        account: Account,
        *,
        kind: str,
        nature: str,
        body: Mapping[str, Any] | None = None,
        evidence_refs: Sequence[str] | None = None,
        source: str = "app_action",
        classification: str = DEFAULT_CLASSIFICATION,
        correlation_id: str = "",
        data_mode: str = DEFAULT_DATA_MODE,
        confidence: float = 1.0,
    ) -> MemoryRecord:
        """Append one record to the tenant's shared org store."""
        return self._append(
            account=account,
            path=self.resolve_org_store(account),
            kind=kind,
            nature=nature,
            body=body,
            evidence_refs=evidence_refs,
            source=source,
            classification=classification,
            correlation_id=correlation_id,
            data_mode=data_mode,
            confidence=confidence,
            basis="org_memory",
            store_kind=ORG_STORE_KIND,
        )

    def _append(
        self,
        *,
        account: Account,
        path: str,
        kind: str,
        nature: str,
        body: Mapping[str, Any] | None,
        evidence_refs: Sequence[str] | None,
        source: str,
        classification: str,
        correlation_id: str,
        data_mode: str,
        confidence: float,
        basis: str,
        store_kind: str,
    ) -> MemoryRecord:
        store = self._open(path, kind=store_kind, account=account)
        resolved_correlation = correlation_id or f"corr-{uuid.uuid4().hex}"
        refs = list(evidence_refs or [])
        record = store.add(
            kind=kind,
            nature=nature,
            tenant_id=account.tenant_id,
            client_id=account.client_id or "",
            actor=account.account_id,
            role_id=account.role_id or "",
            source=source,
            classification=classification,
            timestamp=_now(),
            correlation_id=resolved_correlation,
            confidence=confidence,
            evidence_refs=refs,
            data_mode=data_mode,
            provenance={
                "correlation_id": resolved_correlation,
                "data_mode": data_mode,
                "basis": basis,
                "sources": refs,
            },
            body=dict(body or {}),
        )
        self._index(account=account, path=path, kind=store_kind, store=store)
        return record

    # ----------------------------------------------------------------- reads
    def read(
        self,
        account: Account,
        *,
        limit: int = 50,
        kinds: Sequence[str] | None = None,
    ) -> list[MemoryRecord]:
        """The account's own records, oldest first, capped at the newest `limit`."""
        store = self.store_for(account)
        return _tail(store.retrieve(tenant_id=account.tenant_id, kinds=kinds), limit)

    def read_org(
        self,
        account: Account,
        *,
        limit: int = 50,
        kinds: Sequence[str] | None = None,
    ) -> list[MemoryRecord]:
        """The tenant's shared org records, oldest first, capped at the newest `limit`."""
        store = self.org_store_for(account)
        return _tail(store.retrieve(tenant_id=account.tenant_id, kinds=kinds), limit)

    def verify_chain(self, account: Account) -> tuple[bool, str]:
        """Verify the account's own ledger chain."""
        return self.store_for(account).verify_chain()

    def verify_org_chain(self, account: Account) -> tuple[bool, str]:
        """Verify the tenant's org ledger chain."""
        return self.org_store_for(account).verify_chain()


def _tail(records: list[MemoryRecord], limit: int) -> list[MemoryRecord]:
    if limit <= 0:
        return []
    return records[-limit:]
