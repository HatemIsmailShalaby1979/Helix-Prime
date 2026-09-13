"""Domains, org units, and accounts.

One domain is one tenant. A login is username@domain, so the domain supplies
tenant_id and client_id. Account rows are keyed by (domain_id,
username_normalized), and the unique constraint on that pair is what rejects
a duplicate username within one domain while the same username in another
domain stays legal. Every read resolves the domain first; a caller never
passes its own tenant_id into an account query.
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

HASH_ALGO = "scrypt"
LOCK_MINS = 15


class DuplicateDomain(ValueError):
    """A domain with this name already exists."""


class NoSuchDomain(ValueError):
    """No domain has this name."""


class DuplicateUsername(ValueError):
    """An account with this username already exists in this domain."""


class NoSuchAccount(ValueError):
    """No account has this id in this domain."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_username(username: str) -> str:
    return username.strip().lower()


@dataclass(frozen=True)
class Domain:
    """A tenant-scoping unit. name is the login suffix after the at-sign."""

    domain_id: str
    name: str
    tenant_id: str
    client_id: str | None = None
    status: str = "active"
    created_at: str | None = None


@dataclass(frozen=True)
class OrgUnit:
    """A grouping inside one domain, e.g. a team."""

    unit_id: str
    domain_id: str
    name: str
    parent_unit_id: str | None = None
    kind: str = "team"
    path: str | None = None
    created_at: str | None = None


@dataclass(frozen=True)
class Account:
    """One human or agent login inside one domain.

    tenant_id and client_id come from the owning domain, never from the
    caller. username keeps the typed spelling; username_normalized is the
    lowercase key that carries the unique constraint.
    """

    account_id: str
    domain_id: str
    domain_name: str
    tenant_id: str
    username: str
    username_normalized: str
    display_name: str | None = None
    email: str | None = None
    password_hash: str | None = None
    password_algo: str | None = None
    password_params: str | None = None
    role_id: str | None = None
    org_unit_id: str | None = None
    actor_type: str = "human"
    status: str = "active"
    must_change_password: bool = False
    failed_attempts: int = 0
    locked_until: str | None = None
    client_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    last_login_at: str | None = None
    limits: dict[str, int] = field(default_factory=dict)
    consumed: dict[str, int] = field(default_factory=dict)


class AccountRepository:
    """The read and write surface for domains, org units, and accounts."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_domain(self, name: str, tenant_id: str, *, client_id: str | None = None) -> Domain:
        """Create a domain. Raises DuplicateDomain when the name exists."""
        created_at = _now()
        domain_id = f"domain-{uuid.uuid4().hex}"
        try:
            self.conn.execute(
                """
                INSERT INTO domains (domain_id, name, tenant_id, client_id, status, created_at)
                VALUES (?, ?, ?, ?, 'active', ?)
                """,
                (domain_id, name, tenant_id, client_id, created_at),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateDomain(f"domain {name!r} already exists") from exc
        self.conn.commit()
        return Domain(
            domain_id=domain_id,
            name=name,
            tenant_id=tenant_id,
            client_id=client_id,
            status="active",
            created_at=created_at,
        )

    def get_domain_by_name(self, name: str) -> Domain | None:
        """Return the domain with this name, or None."""
        row = self.conn.execute(
            """
            SELECT domain_id, name, tenant_id, client_id, status, created_at
            FROM domains WHERE name = ?
            """,
            (name,),
        ).fetchone()
        return _domain_from_row(row) if row else None

    def create_org_unit(
        self,
        domain_id: str,
        name: str,
        *,
        parent_unit_id: str | None = None,
        kind: str = "team",
    ) -> OrgUnit:
        """Create an org unit inside one domain."""
        created_at = _now()
        unit_id = f"unit-{uuid.uuid4().hex}"
        if parent_unit_id:
            parent = self.conn.execute(
                "SELECT path FROM org_units WHERE unit_id = ?", (parent_unit_id,)
            ).fetchone()
            path = f"{parent['path']}/{name}" if parent and parent["path"] else f"/{name}"
        else:
            path = f"/{name}"
        self.conn.execute(
            """
            INSERT INTO org_units (unit_id, domain_id, parent_unit_id, name, kind, path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (unit_id, domain_id, parent_unit_id, name, kind, path, created_at),
        )
        self.conn.commit()
        return OrgUnit(
            unit_id=unit_id,
            domain_id=domain_id,
            name=name,
            parent_unit_id=parent_unit_id,
            kind=kind,
            path=path,
            created_at=created_at,
        )

    def list_org_units(self, domain_id: str) -> list[OrgUnit]:
        """List the org units in one domain, oldest first."""
        rows = self.conn.execute(
            """
            SELECT unit_id, domain_id, parent_unit_id, name, kind, path, created_at
            FROM org_units WHERE domain_id = ? ORDER BY created_at
            """,
            (domain_id,),
        ).fetchall()
        return [
            OrgUnit(
                unit_id=row["unit_id"],
                domain_id=row["domain_id"],
                parent_unit_id=row["parent_unit_id"],
                name=row["name"],
                kind=row["kind"],
                path=row["path"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def create_account(
        self,
        domain_id: str,
        username: str,
        *,
        password_hash: str | None = None,
        display_name: str | None = None,
        email: str | None = None,
        role_id: str | None = None,
        org_unit_id: str | None = None,
        actor_type: str = "human",
    ) -> Account:
        """Create an account in one domain. Raises DuplicateUsername when the
        normalized username already exists in that domain."""
        domain = self._require_domain(domain_id)
        created_at = _now()
        account_id = f"account-{uuid.uuid4().hex}"
        username_normalized = _normalise_username(username)
        try:
            self.conn.execute(
                """
                INSERT INTO accounts (
                    account_id, domain_id, username, username_normalized, display_name,
                    email, password_hash, password_algo, password_params, role_id,
                    org_unit_id, actor_type, status, must_change_password,
                    failed_attempts, locked_until, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 0, 0, NULL, ?, ?)
                """,
                (
                    account_id,
                    domain_id,
                    username,
                    username_normalized,
                    display_name,
                    email,
                    password_hash,
                    HASH_ALGO if password_hash else None,
                    self._params_for(password_hash),
                    role_id,
                    org_unit_id,
                    actor_type,
                    created_at,
                    created_at,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateUsername(
                f"username {username!r} already exists in domain {domain.name!r}"
            ) from exc
        self.conn.commit()
        return self.get_account_by_id(account_id)  # type: ignore[return-value]

    def get_account_by_login(self, domain_name: str, username: str) -> Account | None:
        """Return the account for username@domain_name, or None.

        It resolves the domain first, so the tenant scope comes from the
        domain row and a wrong domain name simply finds nothing.
        """
        domain = self.get_domain_by_name(domain_name)
        if domain is None:
            return None
        username_normalized = _normalise_username(username)
        return self._fetch_account(
            """
            SELECT a.account_id, a.domain_id, d.name AS domain_name, d.tenant_id,
                   d.client_id, a.username, a.username_normalized, a.display_name,
                   a.email, a.password_hash, a.password_algo, a.password_params,
                   a.role_id, a.org_unit_id, a.actor_type, a.status,
                   a.must_change_password, a.failed_attempts, a.locked_until,
                   a.created_at, a.updated_at, a.last_login_at
            FROM accounts a
            JOIN domains d ON d.domain_id = a.domain_id
            WHERE a.domain_id = ? AND a.username_normalized = ?
            """,
            (domain.domain_id, username_normalized),
        )

    def get_account_by_id(self, account_id: str) -> Account | None:
        """Return the account with this id, or None."""
        return self._fetch_account(
            """
            SELECT a.account_id, a.domain_id, d.name AS domain_name, d.tenant_id,
                   d.client_id, a.username, a.username_normalized, a.display_name,
                   a.email, a.password_hash, a.password_algo, a.password_params,
                   a.role_id, a.org_unit_id, a.actor_type, a.status,
                   a.must_change_password, a.failed_attempts, a.locked_until,
                   a.created_at, a.updated_at, a.last_login_at
            FROM accounts a
            JOIN domains d ON d.domain_id = a.domain_id
            WHERE a.account_id = ?
            """,
            (account_id,),
        )

    def list_accounts(self, domain_id: str) -> list[Account]:
        """List the accounts in one domain, oldest first."""
        rows = self.conn.execute(
            """
            SELECT a.account_id, a.domain_id, d.name AS domain_name, d.tenant_id,
                   d.client_id, a.username, a.username_normalized, a.display_name,
                   a.email, a.password_hash, a.password_algo, a.password_params,
                   a.role_id, a.org_unit_id, a.actor_type, a.status,
                   a.must_change_password, a.failed_attempts, a.locked_until,
                   a.created_at, a.updated_at, a.last_login_at
            FROM accounts a
            JOIN domains d ON d.domain_id = a.domain_id
            WHERE a.domain_id = ? ORDER BY a.created_at
            """,
            (domain_id,),
        ).fetchall()
        return [_account_from_row(row) for row in rows]

    def update_account(
        self,
        account_id: str,
        *,
        display_name: str | None = None,
        email: str | None = None,
        role_id: str | None = None,
        org_unit_id: str | None = None,
    ) -> Account:
        """Update the mutable profile fields of an account.

        Each field is a separate static UPDATE, so no statement is assembled
        from caller data. A None argument leaves that column unchanged.
        """
        if all(value is None for value in (display_name, email, role_id, org_unit_id)):
            raise ValueError("update_account: nothing to update")
        now = _now()
        if display_name is not None:
            self.conn.execute(
                "UPDATE accounts SET display_name = ?, updated_at = ? WHERE account_id = ?",
                (display_name, now, account_id),
            )
        if email is not None:
            self.conn.execute(
                "UPDATE accounts SET email = ?, updated_at = ? WHERE account_id = ?",
                (email, now, account_id),
            )
        if role_id is not None:
            self.conn.execute(
                "UPDATE accounts SET role_id = ?, updated_at = ? WHERE account_id = ?",
                (role_id, now, account_id),
            )
        if org_unit_id is not None:
            self.conn.execute(
                "UPDATE accounts SET org_unit_id = ?, updated_at = ? WHERE account_id = ?",
                (org_unit_id, now, account_id),
            )
        self.conn.commit()
        return self._require_account(account_id)

    def set_status(self, account_id: str, status: str) -> Account:
        """Set the account status, e.g. active, disabled, terminated."""
        self.conn.execute(
            "UPDATE accounts SET status = ?, updated_at = ? WHERE account_id = ?",
            (status, _now(), account_id),
        )
        self.conn.commit()
        return self._require_account(account_id)

    def record_failed_attempt(self, account_id: str) -> Account:
        """Increment the failed-attempt counter."""
        self.conn.execute(
            """
            UPDATE accounts
            SET failed_attempts = failed_attempts + 1, updated_at = ?
            WHERE account_id = ?
            """,
            (_now(), account_id),
        )
        self.conn.commit()
        return self._require_account(account_id)

    def reset_failed_attempts(self, account_id: str) -> Account:
        """Clear the failed-attempt counter and any lock window."""
        self.conn.execute(
            """
            UPDATE accounts
            SET failed_attempts = 0, locked_until = NULL, updated_at = ?
            WHERE account_id = ?
            """,
            (_now(), account_id),
        )
        self.conn.commit()
        return self._require_account(account_id)

    def set_password(self, account_id: str, password_hash: str) -> Account:
        """Replace the password hash and clear any must-change flag."""
        self.conn.execute(
            """
            UPDATE accounts
            SET password_hash = ?, password_algo = ?, password_params = ?,
                must_change_password = 0, updated_at = ?
            WHERE account_id = ?
            """,
            (password_hash, HASH_ALGO, self._params_for(password_hash), _now(), account_id),
        )
        self.conn.commit()
        return self._require_account(account_id)

    def lock_account(self, account_id: str, *, until: str | None = None) -> Account:
        """Lock the account until the given instant, defaulting to LOCK_MINS."""
        lock_until = until
        if lock_until is None:
            lock_until = (datetime.now(timezone.utc) + timedelta(minutes=LOCK_MINS)).isoformat()
        self.conn.execute(
            "UPDATE accounts SET status = 'locked', locked_until = ?, updated_at = ? WHERE account_id = ?",
            (lock_until, _now(), account_id),
        )
        self.conn.commit()
        return self._require_account(account_id)

    def _require_domain(self, domain_id: str) -> Domain:
        row = self.conn.execute(
            "SELECT domain_id, name, tenant_id, client_id, status, created_at FROM domains WHERE domain_id = ?",
            (domain_id,),
        ).fetchone()
        if row is None:
            raise NoSuchDomain(f"no domain with id {domain_id!r}")
        return _domain_from_row(row)

    def _require_account(self, account_id: str) -> Account:
        account = self.get_account_by_id(account_id)
        if account is None:
            raise NoSuchAccount(f"no account with id {account_id!r}")
        return account

    def _fetch_account(self, sql: str, params: tuple[Any, ...]) -> Account | None:
        row = self.conn.execute(sql, params).fetchone()
        return _account_from_row(row) if row else None

    @staticmethod
    def _params_for(password_hash: str | None) -> str | None:
        if not password_hash:
            return None
        parts = password_hash.split("$")
        if len(parts) == 6:
            return "n={},r={},p={}".format(parts[1], parts[2], parts[3])
        return None


def _domain_from_row(row: sqlite3.Row) -> Domain:
    return Domain(
        domain_id=row["domain_id"],
        name=row["name"],
        tenant_id=row["tenant_id"],
        client_id=row["client_id"],
        status=row["status"],
        created_at=row["created_at"],
    )


def _account_from_row(row: sqlite3.Row) -> Account:
    return Account(
        account_id=row["account_id"],
        domain_id=row["domain_id"],
        domain_name=row["domain_name"],
        tenant_id=row["tenant_id"],
        username=row["username"],
        username_normalized=row["username_normalized"],
        display_name=row["display_name"],
        email=row["email"],
        password_hash=row["password_hash"],
        password_algo=row["password_algo"],
        password_params=row["password_params"],
        role_id=row["role_id"],
        org_unit_id=row["org_unit_id"],
        actor_type=row["actor_type"],
        status=row["status"],
        must_change_password=bool(row["must_change_password"]),
        failed_attempts=row["failed_attempts"] or 0,
        locked_until=row["locked_until"],
        client_id=row["client_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        last_login_at=row["last_login_at"],
    )
