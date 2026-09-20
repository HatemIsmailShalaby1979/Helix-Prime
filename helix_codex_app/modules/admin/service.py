"""Admin writes: users, domains, org units, capabilities, and limits.

The service is the one place an owner or a manager changes the org chart.
The router gates entry with require_permission("admin.users"); this service
re-checks the same permission plus the org-unit scope before every write,
so a future caller that skips the router still fails closed. An owner acts
on the whole domain. A manager acts only inside their own org unit. An
account can never change its own role or grant itself a capability. Every
mutating call lands in the audit trail through record_node() with the full
envelope, before the caller sees the result.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from contracts.vocabulary import APP_RUNTIME_DATA_MODE
from helix_codex_app.db import record_node
from helix_codex_app.errors import NotFoundError, PermissionDenied
from helix_codex_app.security.accounts import (
    Account,
    AccountRepository,
    Domain,
    DuplicateDomain,
    NoSuchAccount,
    NoSuchDomain,
    OrgUnit,
)
from helix_codex_app.security.limits import load_limits
from helix_codex_app.security.passwords import hash_password
from helix_codex_app.security.permissions import has_permission

ADMIN_PERMISSION = "admin.users"
PROVENANCE_SOURCE = "helix_codex_app.admin"
PROVENANCE_DATA_MODE = APP_RUNTIME_DATA_MODE
MIN_PASSWORD_LENGTH = 8

_ALLOWED_STATUSES = frozenset({"active", "disabled", "locked", "terminated"})
_ALLOWED_ROLES = frozenset({"owner", "manager", "employee", "contractor", "external"})


class AdminService:
    """The write surface for owners and managers."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.repo = AccountRepository(conn)

    def list_users(self, actor: Account, domain_id: str | None = None) -> list[Account]:
        """List accounts. An owner lists the whole domain; a manager lists
        only their own org unit. The scope comes from the actor, never the
        request."""
        self._require_admin(actor)
        resolved_domain = domain_id or actor.domain_id
        self._require_own_domain(actor, resolved_domain)
        accounts = self.repo.list_accounts(resolved_domain)
        if self._is_owner(actor):
            return accounts
        unit = self._require_org_unit(actor)
        return [
            account
            for account in accounts
            if account.org_unit_id is not None and account.org_unit_id == unit.unit_id
        ]

    def create_user(
        self,
        actor: Account,
        *,
        username: str,
        password: str,
        domain_id: str,
        display_name: str | None = None,
        email: str | None = None,
        role_id: str = "employee",
        org_unit_id: str | None = None,
    ) -> Account:
        """Create an account in a domain the actor administers."""
        self._require_admin(actor)
        self._require_create_scope(actor, domain_id, org_unit_id)
        self._require_valid_role(role_id)
        self._require_password(password)
        created = self.repo.create_account(
            domain_id,
            username,
            password_hash=hash_password(password),
            display_name=display_name,
            email=email,
            role_id=role_id,
            org_unit_id=org_unit_id,
        )
        record_node(
            self.conn,
            tenant_id=created.tenant_id,
            client_id=created.client_id,
            domain_id=created.domain_id,
            correlation_id=self._correlation_id(),
            classification="internal",
            nature="historical_event",
            created_by=actor.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="admin",
            body={
                "action": "create_user",
                "account_id": created.account_id,
                "username": created.username,
                "role_id": role_id,
                "org_unit_id": org_unit_id,
            },
        )
        return created

    def update_user(
        self,
        actor: Account,
        account_id: str,
        *,
        display_name: str | None = None,
        email: str | None = None,
        role_id: str | None = None,
        org_unit_id: str | None = None,
    ) -> Account:
        """Update profile fields. An account cannot change its own role or
        move its own org unit."""
        self._require_admin(actor)
        target = self._require_managed_account(actor, account_id)
        if role_id is not None:
            self._require_valid_role(role_id)
            if target.account_id == actor.account_id:
                raise PermissionDenied("an account cannot change its own role")
        if org_unit_id is not None and target.account_id == actor.account_id:
            raise PermissionDenied("an account cannot move its own org unit")
        before = {
            "display_name": target.display_name,
            "email": target.email,
            "role_id": target.role_id,
            "org_unit_id": target.org_unit_id,
        }
        updated = self.repo.update_account(
            account_id,
            display_name=display_name,
            email=email,
            role_id=role_id,
            org_unit_id=org_unit_id,
        )
        record_node(
            self.conn,
            tenant_id=updated.tenant_id,
            client_id=updated.client_id,
            domain_id=updated.domain_id,
            correlation_id=self._correlation_id(),
            classification="internal",
            nature="historical_event",
            created_by=actor.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="admin",
            body={
                "action": "update_user",
                "account_id": account_id,
                "before": before,
                "after": {
                    "display_name": updated.display_name,
                    "email": updated.email,
                    "role_id": updated.role_id,
                    "org_unit_id": updated.org_unit_id,
                },
            },
        )
        return updated

    def set_user_status(self, actor: Account, account_id: str, status: str) -> Account:
        """Set an account status: active, disabled, locked, terminated."""
        self._require_admin(actor)
        if status not in _ALLOWED_STATUSES:
            raise ValueError(f"unknown status {status!r}")
        target = self._require_managed_account(actor, account_id)
        if target.account_id == actor.account_id:
            raise PermissionDenied("an account cannot change its own status")
        updated = self.repo.set_status(account_id, status)
        if status != "active":
            self.conn.execute(
                "UPDATE sessions SET revoked_at = ? WHERE account_id = ? AND revoked_at IS NULL",
                (_now(), account_id),
            )
            self.conn.commit()
        record_node(
            self.conn,
            tenant_id=updated.tenant_id,
            client_id=updated.client_id,
            domain_id=updated.domain_id,
            correlation_id=self._correlation_id(),
            classification="internal",
            nature="historical_event",
            created_by=actor.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="admin",
            body={"action": "set_user_status", "account_id": account_id, "status": status},
        )
        return updated

    def grant_capability(self, actor: Account, account_id: str, capability_key: str) -> Account:
        """Enable a capability for an account, unless it is the caller's own."""
        return self._set_capability(actor, account_id, capability_key, enabled=True)

    def revoke_capability(self, actor: Account, account_id: str, capability_key: str) -> Account:
        """Disable a capability for an account, unless it is the caller's own."""
        return self._set_capability(actor, account_id, capability_key, enabled=False)

    def set_limit(
        self,
        actor: Account,
        account_id: str,
        limit_key: str,
        limit_value: int,
        *,
        window: str = "day",
    ) -> Account:
        """Set one quota row. A value below current usage is stored as-is;
        the next check_and_consume raises LimitExceeded, it does not crash."""
        self._require_admin(actor)
        if limit_value < 0:
            raise ValueError("limit_value must not be negative")
        target = self._require_managed_account(actor, account_id)
        self.conn.execute(
            """
            INSERT OR REPLACE INTO account_limits (
                account_id, limit_key, limit_value, window
            ) VALUES (?, ?, ?, ?)
            """,
            (account_id, limit_key, limit_value, window),
        )
        self.conn.commit()
        record_node(
            self.conn,
            tenant_id=target.tenant_id,
            client_id=target.client_id,
            domain_id=target.domain_id,
            correlation_id=self._correlation_id(),
            classification="internal",
            nature="historical_event",
            created_by=actor.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="admin",
            body={
                "action": "set_limit",
                "account_id": account_id,
                "limit_key": limit_key,
                "limit_value": limit_value,
                "window": window,
            },
        )
        return load_limits(self.conn, target)

    def create_domain(
        self,
        actor: Account,
        *,
        name: str,
        tenant_id: str,
        client_id: str | None = None,
    ) -> Domain:
        """Create a domain. Owner only: a domain is a tenant boundary."""
        self._require_owner(actor)
        try:
            domain = self.repo.create_domain(name, tenant_id, client_id=client_id)
        except DuplicateDomain as exc:
            raise ValueError(f"domain name {name!r} is taken") from exc
        record_node(
            self.conn,
            tenant_id=domain.tenant_id,
            client_id=domain.client_id,
            domain_id=domain.domain_id,
            correlation_id=self._correlation_id(),
            classification="internal",
            nature="historical_event",
            created_by=actor.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="admin",
            body={"action": "create_domain", "domain_id": domain.domain_id, "name": name},
        )
        return domain

    def create_org_unit(
        self,
        actor: Account,
        *,
        domain_id: str,
        name: str,
        parent_unit_id: str | None = None,
        kind: str = "team",
    ) -> OrgUnit:
        """Create an org unit inside a domain the actor administers."""
        self._require_admin(actor)
        self._require_own_domain(actor, domain_id)
        try:
            unit = self.repo.create_org_unit(
                domain_id, name, parent_unit_id=parent_unit_id, kind=kind
            )
        except (NoSuchDomain, ValueError) as exc:
            raise NotFoundError(f"cannot create org unit: {exc}") from exc
        record_node(
            self.conn,
            tenant_id=actor.tenant_id,
            client_id=actor.client_id,
            domain_id=domain_id,
            correlation_id=self._correlation_id(),
            classification="internal",
            nature="historical_event",
            created_by=actor.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="admin",
            body={
                "action": "create_org_unit",
                "unit_id": unit.unit_id,
                "domain_id": domain_id,
                "name": name,
            },
        )
        return unit

    def list_domains(self, actor: Account) -> list[Domain]:
        """List domains in the caller's tenant."""
        self._require_admin(actor)
        rows = self.conn.execute(
            "SELECT domain_id, name, tenant_id, client_id, status, created_at"
            " FROM domains WHERE tenant_id = ? ORDER BY created_at",
            (actor.tenant_id,),
        ).fetchall()
        return [
            Domain(
                domain_id=row["domain_id"],
                name=row["name"],
                tenant_id=row["tenant_id"],
                client_id=row["client_id"],
                status=row["status"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def list_org_units(self, actor: Account, domain_id: str | None = None) -> list[OrgUnit]:
        """List org units in a domain the actor administers."""
        self._require_admin(actor)
        resolved = domain_id or actor.domain_id
        self._require_own_domain(actor, resolved)
        return self.repo.list_org_units(resolved)

    def get_managed_user(self, actor: Account, account_id: str) -> Account:
        """Load one account for an admin screen, inside the caller's scope."""
        self._require_admin(actor)
        return self._require_managed_account(actor, account_id)

    def capabilities_of(self, account: Account) -> list[dict[str, Any]]:
        """List the capability rows for an account."""
        rows = self.conn.execute(
            "SELECT capability_key, enabled, granted_by, granted_at"
            " FROM account_capabilities WHERE account_id = ? ORDER BY capability_key",
            (account.account_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def limits_of(self, account: Account) -> dict[str, int]:
        """The limit rows for an account, key to value."""
        loaded = load_limits(self.conn, account)
        return dict(loaded.limits)

    def _set_capability(
        self,
        actor: Account,
        account_id: str,
        capability_key: str,
        *,
        enabled: bool,
    ) -> Account:
        self._require_admin(actor)
        target = self._require_managed_account(actor, account_id)
        if target.account_id == actor.account_id:
            raise PermissionDenied("an account cannot grant or revoke its own capability")
        self.conn.execute(
            """
            INSERT OR REPLACE INTO account_capabilities (
                account_id, capability_key, enabled, granted_by, granted_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (account_id, capability_key, 1 if enabled else 0, actor.account_id, _now()),
        )
        self.conn.commit()
        record_node(
            self.conn,
            tenant_id=target.tenant_id,
            client_id=target.client_id,
            domain_id=target.domain_id,
            correlation_id=self._correlation_id(),
            classification="internal",
            nature="historical_event",
            created_by=actor.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="admin",
            body={
                "action": "grant_capability" if enabled else "revoke_capability",
                "account_id": account_id,
                "capability_key": capability_key,
            },
        )
        return target

    def _require_admin(self, actor: Account) -> None:
        if not has_permission(actor, ADMIN_PERMISSION, self.conn):
            raise PermissionDenied(
                f"admin permission {ADMIN_PERMISSION!r} not granted",
                payload={"account_id": actor.account_id},
            )

    def _require_owner(self, actor: Account) -> None:
        if not self._is_owner(actor):
            raise PermissionDenied(
                "only an owner may create domains",
                payload={"account_id": actor.account_id},
            )

    def _is_owner(self, actor: Account) -> bool:
        return actor.role_id == "owner"

    def _require_create_scope(
        self, actor: Account, domain_id: str, org_unit_id: str | None
    ) -> None:
        self._require_own_domain(actor, domain_id)
        if self._is_owner(actor):
            return
        unit = self._require_org_unit(actor)
        if org_unit_id != unit.unit_id:
            raise PermissionDenied(
                "a manager may create accounts only inside their own org unit",
                payload={"actor_unit": unit.unit_id, "requested_unit": org_unit_id},
            )

    def _require_managed_account(self, actor: Account, account_id: str) -> Account:
        try:
            target = self.repo.get_account_by_id(account_id)
        except NoSuchAccount as exc:
            raise NotFoundError(f"no account with id {account_id!r}") from exc
        if target is None:
            raise NotFoundError(f"no account with id {account_id!r}")
        if target.domain_id != actor.domain_id:
            raise NotFoundError(f"no account with id {account_id!r}")
        if self._is_owner(actor):
            return target
        unit = self._require_org_unit(actor)
        if target.org_unit_id is None or target.org_unit_id != unit.unit_id:
            raise PermissionDenied(
                "a manager may manage only accounts inside their own org unit",
                payload={
                    "actor_unit": unit.unit_id,
                    "target_unit": target.org_unit_id,
                    "target_account_id": target.account_id,
                },
            )
        return target

    def _require_own_domain(self, actor: Account, domain_id: str) -> None:
        if domain_id != actor.domain_id:
            raise PermissionDenied(
                "admin actions stay inside the caller's own domain",
                payload={"actor_domain": actor.domain_id, "requested_domain": domain_id},
            )

    def _require_org_unit(self, actor: Account) -> OrgUnit:
        if not actor.org_unit_id:
            raise PermissionDenied(
                "a manager without an org unit cannot manage accounts",
                payload={"account_id": actor.account_id},
            )
        try:
            unit = self.repo.get_org_unit(actor.org_unit_id)
        except (NoSuchDomain, ValueError) as exc:
            raise NotFoundError(f"no org unit with id {actor.org_unit_id!r}") from exc
        if unit is None:
            raise NotFoundError(f"no org unit with id {actor.org_unit_id!r}")
        return unit

    def _require_valid_role(self, role_id: str) -> None:
        if role_id not in _ALLOWED_ROLES:
            raise ValueError(f"unknown role {role_id!r}; expected one of {sorted(_ALLOWED_ROLES)}")

    def _require_password(self, password: str) -> None:
        if not password or len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"the password must be at least {MIN_PASSWORD_LENGTH} characters long")

    @staticmethod
    def _correlation_id() -> str:
        return f"admin-{uuid.uuid4().hex}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
