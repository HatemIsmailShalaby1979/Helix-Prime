"""The storage layer for calendar events, attendees, and on-call shifts.

Events are tenant-scoped and visible only to the creator and the invited
attendees. A cancelled event flips its status to "cancelled" and is excluded
from range listings while the event row and its governed nodes stay in place.
Recurrence is one text rule ("daily" or "weekly") stored on the event and
expanded into occurrences when the event is read; occurrences are never
materialised as rows. On-call shifts are tenant-scoped rosters with a primary
and a backup account; the roster text column stores the JSON list of assigned
account ids, and reads treat a missing window as a gap rather than empty.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from helix_codex_app.errors import NotFoundError

CONFIRMED = "confirmed"
CANCELLED = "cancelled"
EVENT_STATUSES: tuple[str, ...] = (CONFIRMED, CANCELLED)

PENDING = "pending"
RESPONSES: tuple[str, ...] = ("yes", "no", "maybe")
RECURRENCE_RULES: tuple[str, ...] = ("", "daily", "weekly")

MAX_ATTENDEES = 64
MAX_OCCURRENCES = 400


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _parse(value: str) -> datetime:
    """Parse an ISO timestamp, treating a naive value as UTC."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _fmt(value: datetime) -> str:
    """Format a timestamp as tz-aware UTC ISO."""
    return value.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class EventAttendee:
    """One invited account and its RSVP response."""

    account_id: str
    response: str


@dataclass(frozen=True)
class Event:
    """One event row with its attendee set."""

    event_id: str
    tenant_id: str
    domain_id: str | None
    title: str
    kind: str
    starts_at: str
    ends_at: str
    all_day: bool
    location: str | None
    room_id: str | None
    creator_account_id: str
    recurrence_rule: str
    created_at: str
    updated_at: str
    status: str
    attendees: tuple[EventAttendee, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "tenant_id": self.tenant_id,
            "domain_id": self.domain_id,
            "title": self.title,
            "kind": self.kind,
            "starts_at": self.starts_at,
            "ends_at": self.ends_at,
            "all_day": self.all_day,
            "location": self.location,
            "room_id": self.room_id,
            "creator_account_id": self.creator_account_id,
            "recurrence_rule": self.recurrence_rule,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "attendees": [
                {"account_id": attendee.account_id, "response": attendee.response}
                for attendee in self.attendees
            ],
        }


@dataclass(frozen=True)
class OnCallShift:
    """One rostered on-call window with a primary and a backup account."""

    shift_id: str
    tenant_id: str
    domain_id: str | None
    roster: tuple[str, ...]
    starts_at: str
    ends_at: str
    primary_account_id: str
    backup_account_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "shift_id": self.shift_id,
            "tenant_id": self.tenant_id,
            "domain_id": self.domain_id,
            "roster": list(self.roster),
            "starts_at": self.starts_at,
            "ends_at": self.ends_at,
            "primary_account_id": self.primary_account_id,
            "backup_account_id": self.backup_account_id,
        }


@dataclass(frozen=True)
class OnCallCoverage:
    """The on-call state at one instant: covered or a gap.

    A window with no rostered shift is a gap, reported as a coverage object
    with covered=False — never as an empty list, which a caller could confuse
    with "no answer".
    """

    covered: bool
    shift: OnCallShift | None
    status: str = "covered"

    def to_dict(self) -> dict[str, Any]:
        return {
            "covered": self.covered,
            "status": self.status,
            "shift": None if self.shift is None else self.shift.to_dict(),
        }


class CalendarRepository:
    """The read and write surface for events and event attendees."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def create_event(
        self,
        *,
        tenant_id: str,
        domain_id: str | None,
        title: str,
        kind: str,
        starts_at: str,
        ends_at: str,
        all_day: bool,
        location: str | None,
        room_id: str | None,
        creator_account_id: str,
        recurrence_rule: str,
        attendee_account_ids: tuple[str, ...],
    ) -> Event:
        event_id = _new_id("event")
        now = _now()
        self.conn.execute(
            """
            INSERT INTO events (
                event_id, tenant_id, domain_id, title, kind, starts_at, ends_at,
                all_day, location, room_id, creator_account_id, recurrence_rule,
                created_at, updated_at, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                tenant_id,
                domain_id,
                title,
                kind,
                starts_at,
                ends_at,
                1 if all_day else 0,
                location,
                room_id,
                creator_account_id,
                recurrence_rule,
                now,
                now,
                CONFIRMED,
            ),
        )
        for account_id in attendee_account_ids:
            self.conn.execute(
                "INSERT INTO event_attendees (event_id, account_id, response) VALUES (?, ?, ?)",
                (event_id, account_id, PENDING),
            )
        self.conn.commit()
        return self.get_event(event_id, tenant_id, creator_account_id)

    def get_event(self, event_id: str, tenant_id: str, account_id: str) -> Event:
        """One event, visible only to its creator or one of its attendees."""
        row = self.conn.execute(
            """
            SELECT event_id, tenant_id, domain_id, title, kind, starts_at, ends_at,
                   all_day, location, room_id, creator_account_id, recurrence_rule,
                   created_at, updated_at, status
            FROM events
            WHERE event_id = ? AND tenant_id = ?
              AND (creator_account_id = ? OR EXISTS (
                    SELECT 1 FROM event_attendees
                    WHERE event_id = events.event_id AND account_id = ?))
            """,
            (event_id, tenant_id, account_id, account_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("event not found")
        return self._event_from_row(row)

    def list_events(
        self,
        *,
        tenant_id: str,
        account_id: str,
        from_at: str,
        to_at: str,
    ) -> list[Event]:
        """Confirmed events, and their recurrences, inside [from_at, to_at).

        The range is inclusive of the start and exclusive of the end. Only
        events the account created or is invited to are considered, and they
        are expanded recurrence-first then ordered by occurrence time.
        """
        from_dt = _parse(from_at)
        to_dt = _parse(to_at)
        rows = self.conn.execute(
            """
            SELECT event_id, tenant_id, domain_id, title, kind, starts_at, ends_at,
                   all_day, location, room_id, creator_account_id, recurrence_rule,
                   created_at, updated_at, status
            FROM events
            WHERE tenant_id = ? AND status = ?
              AND (creator_account_id = ? OR EXISTS (
                    SELECT 1 FROM event_attendees
                    WHERE event_id = events.event_id AND account_id = ?))
            ORDER BY starts_at ASC, rowid ASC
            """,
            (tenant_id, CONFIRMED, account_id, account_id),
        ).fetchall()
        occurrences: list[Event] = []
        for row in rows:
            occurrences.extend(self._expand(self._event_from_row(row), from_dt, to_dt))
        occurrences.sort(key=lambda event: event.starts_at)
        return occurrences

    def update_event(
        self,
        event_id: str,
        tenant_id: str,
        *,
        title: str | None = None,
        kind: str | None = None,
        starts_at: str | None = None,
        ends_at: str | None = None,
        all_day: bool | None = None,
        location: str | None = None,
        room_id: str | None = None,
        recurrence_rule: str | None = None,
    ) -> Event:
        """Update the mutable fields of a confirmed event.

        Each field is a separate static UPDATE, so no statement is assembled
        from caller data.
        """
        now = _now()
        if title is not None:
            self.conn.execute(
                "UPDATE events SET title = ?, updated_at = ? "
                "WHERE event_id = ? AND tenant_id = ?",
                (title, now, event_id, tenant_id),
            )
        if kind is not None:
            self.conn.execute(
                "UPDATE events SET kind = ?, updated_at = ? "
                "WHERE event_id = ? AND tenant_id = ?",
                (kind, now, event_id, tenant_id),
            )
        if starts_at is not None:
            self.conn.execute(
                "UPDATE events SET starts_at = ?, updated_at = ? "
                "WHERE event_id = ? AND tenant_id = ?",
                (starts_at, now, event_id, tenant_id),
            )
        if ends_at is not None:
            self.conn.execute(
                "UPDATE events SET ends_at = ?, updated_at = ? "
                "WHERE event_id = ? AND tenant_id = ?",
                (ends_at, now, event_id, tenant_id),
            )
        if all_day is not None:
            self.conn.execute(
                "UPDATE events SET all_day = ?, updated_at = ? "
                "WHERE event_id = ? AND tenant_id = ?",
                (1 if all_day else 0, now, event_id, tenant_id),
            )
        if location is not None:
            self.conn.execute(
                "UPDATE events SET location = ?, updated_at = ? "
                "WHERE event_id = ? AND tenant_id = ?",
                (location, now, event_id, tenant_id),
            )
        if room_id is not None:
            self.conn.execute(
                "UPDATE events SET room_id = ?, updated_at = ? "
                "WHERE event_id = ? AND tenant_id = ?",
                (room_id, now, event_id, tenant_id),
            )
        if recurrence_rule is not None:
            self.conn.execute(
                "UPDATE events SET recurrence_rule = ?, updated_at = ? "
                "WHERE event_id = ? AND tenant_id = ?",
                (recurrence_rule, now, event_id, tenant_id),
            )
        self.conn.commit()
        return self._get_by_id(event_id, tenant_id)

    def set_attendees(
        self,
        event_id: str,
        tenant_id: str,
        account_ids: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Replace the attendee set, keeping the RSVP of retained attendees.

        Returns the account ids that were newly added, so the caller can
        notify exactly once per new attendee.
        """
        rows = self.conn.execute(
            "SELECT account_id FROM event_attendees WHERE event_id = ?",
            (event_id,),
        ).fetchall()
        existing = {row["account_id"] for row in rows}
        keep = set(account_ids)
        for row in rows:
            if row["account_id"] not in keep:
                self.conn.execute(
                    "DELETE FROM event_attendees WHERE event_id = ? AND account_id = ?",
                    (event_id, row["account_id"]),
                )
        for account_id in account_ids:
            if account_id not in existing:
                self.conn.execute(
                    "INSERT INTO event_attendees (event_id, account_id, response) "
                    "VALUES (?, ?, ?)",
                    (event_id, account_id, PENDING),
                )
        self.conn.commit()
        return tuple(account_id for account_id in account_ids if account_id not in existing)

    def respond(self, event_id: str, tenant_id: str, account_id: str, response: str) -> Event:
        """Record an attendee's RSVP. A non-attendee gets NotFoundError."""
        rowcount = self.conn.execute(
            """
            UPDATE event_attendees
            SET response = ?
            WHERE event_id = ? AND account_id = ?
              AND EXISTS (
                    SELECT 1 FROM events
                    WHERE event_id = event_attendees.event_id AND tenant_id = ?)
            """,
            (response, event_id, account_id, tenant_id),
        ).rowcount
        if not rowcount:
            raise NotFoundError("event not found")
        self.conn.commit()
        return self.get_event(event_id, tenant_id, account_id)

    def cancel_event(self, event_id: str, tenant_id: str) -> Event:
        """Soft-delete a confirmed event: status flips, the row stays."""
        rowcount = self.conn.execute(
            "UPDATE events SET status = ?, updated_at = ? "
            "WHERE event_id = ? AND tenant_id = ? AND status = ?",
            (CANCELLED, _now(), event_id, tenant_id, CONFIRMED),
        ).rowcount
        if not rowcount:
            raise NotFoundError("event not found")
        self.conn.commit()
        return self._get_by_id(event_id, tenant_id)

    def resolve_attendees(self, tenant_id: str, account_ids: tuple[str, ...]) -> set[str]:
        """The account ids that exist inside the tenant's domain(s)."""
        resolved: set[str] = set()
        for account_id in account_ids:
            row = self.conn.execute(
                """
                SELECT a.account_id
                FROM accounts a
                JOIN domains d ON a.domain_id = d.domain_id
                WHERE a.account_id = ? AND d.tenant_id = ?
                """,
                (account_id, tenant_id),
            ).fetchone()
            if row is not None:
                resolved.add(row["account_id"])
        return resolved

    def create_shift(
        self,
        *,
        tenant_id: str,
        domain_id: str | None,
        starts_at: str,
        ends_at: str,
        primary_account_id: str,
        backup_account_id: str,
    ) -> OnCallShift:
        """Insert one on-call shift. The roster text stores the account ids."""
        shift_id = _new_id("shift")
        roster = json.dumps([primary_account_id, backup_account_id])
        self.conn.execute(
            """
            INSERT INTO oncall_shifts (
                shift_id, tenant_id, domain_id, roster, starts_at, ends_at,
                primary_account_id, backup_account_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                shift_id,
                tenant_id,
                domain_id,
                roster,
                starts_at,
                ends_at,
                primary_account_id,
                backup_account_id,
            ),
        )
        self.conn.commit()
        return self._get_shift(shift_id, tenant_id)

    def get_current_shift(self, tenant_id: str, at: str) -> OnCallShift | None:
        """The shift covering `at` (start inclusive, end exclusive), or None.

        A None result is a coverage gap: there is no rostered shift for this
        instant. No limit is applied so the earliest open window with the
        latest start wins; shifts never overlap, so at most one matches.
        """
        row = self.conn.execute(
            """
            SELECT shift_id, tenant_id, domain_id, roster, starts_at, ends_at,
                   primary_account_id, backup_account_id
            FROM oncall_shifts
            WHERE tenant_id = ? AND starts_at <= ? AND ends_at > ?
            ORDER BY starts_at DESC, rowid DESC
            LIMIT 1
            """,
            (tenant_id, at, at),
        ).fetchone()
        if row is None:
            return None
        return self._shift_from_row(row)

    def get_next_shift(self, tenant_id: str, after_at: str) -> OnCallShift | None:
        """The earliest shift that starts after `after_at`, or None."""
        row = self.conn.execute(
            """
            SELECT shift_id, tenant_id, domain_id, roster, starts_at, ends_at,
                   primary_account_id, backup_account_id
            FROM oncall_shifts
            WHERE tenant_id = ? AND starts_at > ?
            ORDER BY starts_at ASC, rowid ASC
            LIMIT 1
            """,
            (tenant_id, after_at),
        ).fetchone()
        if row is None:
            return None
        return self._shift_from_row(row)

    def list_shifts(
        self,
        *,
        tenant_id: str,
        from_at: str,
        to_at: str,
    ) -> list[OnCallShift]:
        """Shifts overlapping [from_at, to_at), ordered by start time.

        An overlapping shift is one that started before the window closes and
        ends after the window opens: [from, to) is start-inclusive and
        end-exclusive exactly as for events.
        """
        rows = self.conn.execute(
            """
            SELECT shift_id, tenant_id, domain_id, roster, starts_at, ends_at,
                   primary_account_id, backup_account_id
            FROM oncall_shifts
            WHERE tenant_id = ? AND starts_at < ? AND ends_at > ?
            ORDER BY starts_at ASC, rowid ASC
            """,
            (tenant_id, to_at, from_at),
        ).fetchall()
        return [self._shift_from_row(row) for row in rows]

    def list_account_shifts(
        self,
        *,
        account_id: str,
        tenant_id: str,
        from_at: str,
    ) -> list[OnCallShift]:
        """Upcoming shifts where the account is primary or backup."""
        rows = self.conn.execute(
            """
            SELECT shift_id, tenant_id, domain_id, roster, starts_at, ends_at,
                   primary_account_id, backup_account_id
            FROM oncall_shifts
            WHERE tenant_id = ?
              AND (primary_account_id = ? OR backup_account_id = ?)
              AND ends_at > ?
            ORDER BY starts_at ASC, rowid ASC
            """,
            (tenant_id, account_id, account_id, from_at),
        ).fetchall()
        return [self._shift_from_row(row) for row in rows]

    def _get_shift(self, shift_id: str, tenant_id: str) -> OnCallShift:
        row = self.conn.execute(
            """
            SELECT shift_id, tenant_id, domain_id, roster, starts_at, ends_at,
                   primary_account_id, backup_account_id
            FROM oncall_shifts
            WHERE shift_id = ? AND tenant_id = ?
            """,
            (shift_id, tenant_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("shift not found")
        return self._shift_from_row(row)

    def _shift_from_row(self, row: sqlite3.Row) -> OnCallShift:
        try:
            roster = tuple(json.loads(row["roster"] or "[]"))
        except (ValueError, TypeError):
            roster = ()
        return OnCallShift(
            shift_id=row["shift_id"],
            tenant_id=row["tenant_id"],
            domain_id=row["domain_id"],
            roster=roster,
            starts_at=row["starts_at"],
            ends_at=row["ends_at"],
            primary_account_id=row["primary_account_id"],
            backup_account_id=row["backup_account_id"],
        )

    def _get_by_id(self, event_id: str, tenant_id: str) -> Event:
        row = self.conn.execute(
            """
            SELECT event_id, tenant_id, domain_id, title, kind, starts_at, ends_at,
                   all_day, location, room_id, creator_account_id, recurrence_rule,
                   created_at, updated_at, status
            FROM events
            WHERE event_id = ? AND tenant_id = ?
            """,
            (event_id, tenant_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("event not found")
        return self._event_from_row(row)

    def _event_from_row(self, row: sqlite3.Row) -> Event:
        return Event(
            event_id=row["event_id"],
            tenant_id=row["tenant_id"],
            domain_id=row["domain_id"],
            title=row["title"],
            kind=row["kind"],
            starts_at=row["starts_at"],
            ends_at=row["ends_at"],
            all_day=bool(row["all_day"]),
            location=row["location"],
            room_id=row["room_id"],
            creator_account_id=row["creator_account_id"],
            recurrence_rule=row["recurrence_rule"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            status=row["status"],
            attendees=self._attendees(row["event_id"]),
        )

    def _attendees(self, event_id: str) -> tuple[EventAttendee, ...]:
        rows = self.conn.execute(
            "SELECT account_id, response FROM event_attendees WHERE event_id = ? ORDER BY rowid ASC",
            (event_id,),
        ).fetchall()
        return tuple(
            EventAttendee(account_id=row["account_id"], response=row["response"]) for row in rows
        )

    def _expand(self, event: Event, from_dt: datetime, to_dt: datetime) -> list[Event]:
        start = _parse(event.starts_at)
        delta = _parse(event.ends_at) - start
        if event.recurrence_rule == "daily":
            step = timedelta(days=1)
        elif event.recurrence_rule == "weekly":
            step = timedelta(days=7)
        else:
            if from_dt <= start < to_dt:
                return [event]
            return []
        occurrences: list[Event] = []
        cursor = start
        count = 0
        while cursor < to_dt and count < MAX_OCCURRENCES:
            if from_dt <= cursor:
                occurrences.append(self._occurrence(event, _fmt(cursor), _fmt(cursor + delta)))
            cursor = cursor + step
            count += 1
        return occurrences

    def _occurrence(self, event: Event, starts_at: str, ends_at: str) -> Event:
        return Event(
            event_id=event.event_id,
            tenant_id=event.tenant_id,
            domain_id=event.domain_id,
            title=event.title,
            kind=event.kind,
            starts_at=starts_at,
            ends_at=ends_at,
            all_day=event.all_day,
            location=event.location,
            room_id=event.room_id,
            creator_account_id=event.creator_account_id,
            recurrence_rule=event.recurrence_rule,
            created_at=event.created_at,
            updated_at=event.updated_at,
            status=event.status,
            attendees=event.attendees,
        )
