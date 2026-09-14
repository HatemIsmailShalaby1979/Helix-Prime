"""The storage layer for attendance punches.

A punch is one immutable row: who (account), when (punched_at), from which
device, and with which correlation id. Punches are append-only; a correction
is a new row with a note, never an edit to a prior row. The server decides
punched_at — a caller-supplied time is never accepted here or in the service.
An account has at most one open punch: the open one is simply the most recent
row of type "in", read with (punched_at, rowid) ordering so two punches at the
same microsecond still resolve deterministically.
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

PUNCH_IN = "in"
PUNCH_OUT = "out"
PUNCH_TYPES: tuple[str, ...] = (PUNCH_IN, PUNCH_OUT)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _parse(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _fmt(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class PunchRecord:
    """One immutable punch row."""

    punch_id: str
    account_id: str
    domain_id: str | None
    tenant_id: str
    punch_type: str
    punched_at: str
    source: str | None = None
    geo: str | None = None
    note: str | None = None
    device_id: str | None = None
    correlation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "punch_id": self.punch_id,
            "account_id": self.account_id,
            "domain_id": self.domain_id,
            "tenant_id": self.tenant_id,
            "punch_type": self.punch_type,
            "punched_at": self.punched_at,
            "source": self.source,
            "geo": self.geo,
            "note": self.note,
            "device_id": self.device_id,
            "correlation_id": self.correlation_id,
        }


class AttendanceRepository:
    """The read and write surface for punch records."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def insert_punch(
        self,
        *,
        tenant_id: str,
        domain_id: str | None,
        account_id: str,
        punch_type: str,
        punched_at: str | None = None,
        source: str | None = None,
        geo: str | None = None,
        note: str | None = None,
        device_id: str | None = None,
        correlation_id: str | None = None,
    ) -> PunchRecord:
        """Append one punch row. Never updates or deletes an existing row."""
        if punch_type not in PUNCH_TYPES:
            raise ValueError(f"punch_type must be one of {', '.join(PUNCH_TYPES)}")
        punch_id = _new_id("punch")
        resolved_at = punched_at or _now()
        resolved_correlation = correlation_id or f"punch-{uuid.uuid4().hex}"
        self.conn.execute(
            """
            INSERT INTO punch_records (
                punch_id, account_id, domain_id, tenant_id, punch_type, punched_at,
                source, geo, note, device_id, correlation_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                punch_id,
                account_id,
                domain_id,
                tenant_id,
                punch_type,
                resolved_at,
                source,
                geo,
                note,
                device_id,
                resolved_correlation,
            ),
        )
        self.conn.commit()
        return PunchRecord(
            punch_id=punch_id,
            account_id=account_id,
            domain_id=domain_id,
            tenant_id=tenant_id,
            punch_type=punch_type,
            punched_at=resolved_at,
            source=source,
            geo=geo,
            note=note,
            device_id=device_id,
            correlation_id=resolved_correlation,
        )

    def latest_punch(self, tenant_id: str, account_id: str) -> PunchRecord | None:
        """The most recent punch for one account, or None when none exists."""
        row = self.conn.execute(
            """
            SELECT punch_id, account_id, domain_id, tenant_id, punch_type,
                   punched_at, source, geo, note, device_id, correlation_id
            FROM punch_records
            WHERE tenant_id = ? AND account_id = ?
            ORDER BY punched_at DESC, rowid DESC
            LIMIT 1
            """,
            (tenant_id, account_id),
        ).fetchone()
        return self._from_row(row) if row is not None else None

    def list_records(
        self,
        *,
        tenant_id: str,
        account_ids: tuple[str, ...],
        from_at: str,
        to_at: str,
    ) -> list[PunchRecord]:
        """Punch rows inside [from_at, to_at) for the given accounts.

        The range is inclusive of the start and exclusive of the end, and rows
        are ordered by (punched_at, rowid) so pairing stays deterministic.
        """
        if not account_ids:
            return []
        sql = """
            SELECT punch_id, account_id, domain_id, tenant_id, punch_type,
                   punched_at, source, geo, note, device_id, correlation_id
            FROM punch_records
            WHERE tenant_id = ?
        """
        placeholders = ", ".join("?" for _ in account_ids)
        sql += f" AND account_id IN ({placeholders})"
        sql += " AND punched_at >= ? AND punched_at < ?"
        sql += " ORDER BY punched_at ASC, rowid ASC"
        rows = self.conn.execute(sql, (tenant_id, *account_ids, from_at, to_at)).fetchall()
        return [self._from_row(row) for row in rows]

    def records_after(
        self,
        *,
        tenant_id: str,
        account_ids: tuple[str, ...],
        from_at: str,
    ) -> dict[str, list[PunchRecord]]:
        """Punches at or after from_at, grouped per account, in row order.

        The pairing walk needs the closing "out" even when it lands after the
        window end, so this read has no upper bound and returns the group for
        each account as a list ordered by (punched_at, rowid).
        """
        if not account_ids:
            return {}
        sql = """
            SELECT punch_id, account_id, domain_id, tenant_id, punch_type,
                   punched_at, source, geo, note, device_id, correlation_id
            FROM punch_records
            WHERE tenant_id = ?
        """
        placeholders = ", ".join("?" for _ in account_ids)
        sql += f" AND account_id IN ({placeholders})"
        sql += " AND punched_at >= ?"
        sql += " ORDER BY account_id ASC, punched_at ASC, rowid ASC"
        rows = self.conn.execute(sql, (tenant_id, *account_ids, from_at)).fetchall()
        grouped: dict[str, list[PunchRecord]] = {}
        for row in rows:
            record = self._from_row(row)
            grouped.setdefault(record.account_id, []).append(record)
        return grouped

    def _from_row(self, row: sqlite3.Row) -> PunchRecord:
        return PunchRecord(
            punch_id=row["punch_id"],
            account_id=row["account_id"],
            domain_id=row["domain_id"],
            tenant_id=row["tenant_id"],
            punch_type=row["punch_type"],
            punched_at=row["punched_at"],
            source=row["source"],
            geo=row["geo"],
            note=row["note"],
            device_id=row["device_id"],
            correlation_id=row["correlation_id"],
        )
