"""Attendance writes and the manager-trustworthy summary.

The service owns the punch rules and the governed envelope:
1. Punches are append-only rows. Punching in while a punch is already open
   raises ValueError; punching out with nothing open raises ValueError. The
   timestamp is always decided here from the server clock — a caller-supplied
   time is never accepted.
2. Every punch writes one governed node sharing the punch row's correlation_id
   so each tap reads as one story in the audit trail.
3. Visibility is role-scoped. An owner sees the whole domain. A manager sees
   their own org unit. Anyone else sees only their own punches. A manager
   without an org unit falls back to self-only, never a wider scope.
4. The summary counts only completed in/out pairs, buckets each pair's minutes
   to the punch-in UTC date, and reports per-day and total minutes. An open
   punch that has not been closed yet contributes zero to the summary; the
   punch clock's running total separately accrues the open segment.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from contracts.vocabulary import APP_RUNTIME_DATA_MODE
from helix_codex_app.db import record_node
from helix_codex_app.modules.attendance.repository import (
    PUNCH_IN,
    PUNCH_OUT,
    AttendanceRepository,
    PunchRecord,
    _parse,
)
from helix_codex_app.security.accounts import Account, AccountRepository

PROVENANCE_SOURCE = "helix_codex_app.attendance"
PROVENANCE_DATA_MODE = APP_RUNTIME_DATA_MODE
OWNER_ROLE = "owner"
MANAGER_ROLE = "manager"


class AttendanceService:
    """Punch in/out, status, records, and the worked-minutes summary."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.repo = AttendanceRepository(conn)
        self.accounts = AccountRepository(conn)

    def punch_in(
        self,
        account: Account,
        *,
        source: str | None = None,
        device_id: str | None = None,
    ) -> PunchRecord:
        """Open a punch for the account, recording one governed node.

        The timestamp comes from the server clock here, never from the caller.
        A punch that is already open makes this raise ValueError.
        """
        open_punch = self.current_status(account)
        if open_punch is not None:
            raise ValueError("a punch is already open")
        punch = self.repo.insert_punch(
            tenant_id=account.tenant_id,
            domain_id=account.domain_id,
            account_id=account.account_id,
            punch_type=PUNCH_IN,
            source=source,
            device_id=device_id,
        )
        self._record_node(account, punch)
        return punch

    def punch_out(self, account: Account) -> PunchRecord:
        """Close the open punch, recording one governed node.

        Punching out with nothing open raises ValueError.
        """
        open_punch = self.current_status(account)
        if open_punch is None:
            raise ValueError("no punch is open")
        punch = self.repo.insert_punch(
            tenant_id=account.tenant_id,
            domain_id=account.domain_id,
            account_id=account.account_id,
            punch_type=PUNCH_OUT,
        )
        self._record_node(account, punch)
        return punch

    def current_status(self, account: Account) -> PunchRecord | None:
        """The account's open punch, or None when the account is off the clock.

        A punch is open exactly when the most recent punch row is an "in" —
        append-only writes and the one-open-punch rule make that test exact.
        """
        latest = self.repo.latest_punch(account.tenant_id, account.account_id)
        if latest is None or latest.punch_type != PUNCH_IN:
            return None
        return latest

    def list_records(
        self,
        account: Account,
        from_at: str,
        to_at: str,
    ) -> list[PunchRecord]:
        """Punch rows visible to the account inside [from_at, to_at)."""
        return self.repo.list_records(
            tenant_id=account.tenant_id,
            account_ids=self._visible_account_ids(account),
            from_at=from_at,
            to_at=to_at,
        )

    def summary(self, account: Account, from_at: str, to_at: str) -> dict[str, object]:
        """Worked minutes per day plus a total, for the visible scope.

        Each completed in/out pair is counted once, with its minutes bucketed
        to the punch-in UTC date, only when the punch-in lies inside
        [from_at, to_at). The total is the sum of those days.
        """
        from_dt = _parse(from_at)
        to_dt = _parse(to_at)
        if to_dt <= from_dt:
            raise ValueError("the window must end after it starts")
        grouped = self.repo.records_after(
            tenant_id=account.tenant_id,
            account_ids=self._visible_account_ids(account),
            from_at=from_at,
        )
        days: dict[str, int] = {}
        for records in grouped.values():
            open_at: datetime | None = None
            for record in records:
                at = _parse(record.punched_at)
                if record.punch_type == PUNCH_IN:
                    open_at = at
                    continue
                if open_at is None:
                    continue
                if from_dt <= open_at < to_dt:
                    minutes = max(0, int((at - open_at).total_seconds() // 60))
                    if minutes:
                        key = open_at.date().isoformat()
                        days[key] = days.get(key, 0) + minutes
                open_at = None
        ordered = [{"date": key, "minutes": days[key]} for key in sorted(days)]
        return {
            "from": from_at,
            "to": to_at,
            "days": ordered,
            "total_minutes": sum(days.values()),
        }

    def today_minutes(self, account: Account) -> int:
        """The account's own running total for today, including an open punch.

        The open segment accrues from the later of its punch-in and midnight,
        so the punch clock's total moves while the account is on the clock.
        """
        now = datetime.now(timezone.utc)
        day_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
        result = self.summary(
            account, day_start.isoformat(), (day_start + timedelta(days=1)).isoformat()
        )
        minutes = int(result["total_minutes"])
        open_punch = self.current_status(account)
        if open_punch is not None:
            start = max(_parse(open_punch.punched_at), day_start)
            if start < now:
                minutes += int((now - start).total_seconds() // 60)
        return minutes

    def _visible_account_ids(self, account: Account) -> tuple[str, ...]:
        if account.role_id == OWNER_ROLE:
            return tuple(a.account_id for a in self.accounts.list_accounts(account.domain_id))
        if account.role_id == MANAGER_ROLE:
            members: list[str] = [account.account_id]
            if account.org_unit_id:
                members.extend(
                    a.account_id
                    for a in self.accounts.list_accounts(account.domain_id)
                    if a.org_unit_id == account.org_unit_id
                )
            return tuple(dict.fromkeys(members))
        return (account.account_id,)

    def _record_node(self, account: Account, punch: PunchRecord) -> None:
        record_node(
            self.conn,
            tenant_id=account.tenant_id,
            client_id=account.client_id,
            domain_id=account.domain_id,
            correlation_id=punch.correlation_id or f"punch-{punch.punch_id}",
            classification="internal",
            nature="user_claim",
            created_by=account.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="punch",
            body={
                "punch_id": punch.punch_id,
                "account_id": punch.account_id,
                "punch_type": punch.punch_type,
                "punched_at": punch.punched_at,
                "source": punch.source,
                "device_id": punch.device_id,
            },
        )
