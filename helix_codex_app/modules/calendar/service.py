"""The write and read surface for events and on-call rosters, with the
governance envelope.

The service owns two jobs:
1. CRUD on event and attendee rows (delegated to the repository) plus the
   governed envelope (record_node) so every event write lands in the audit
   trail. Events are visible only to their creator and invited attendees,
   and a cancellation is a soft status flip: the event row stays and the
   audit trail keeps its nodes.
2. Notification: adding an attendee fires exactly one "event_invite"
   notification per new attendee through the shared NotificationService.
3. On-call: shifts with a primary and a backup. Creating a shift is a
   roster assignment, so it is gated to managers; reads are open to any
   tenant member. A window with no shift is a coverage gap reported as
   OnCallCoverage(covered=False), never as an empty list.

Updating an event or cancelling it is gated by a steward check: only the
creator or a manager may do it. Responding to an event requires being one
of its attendees, which the repository enforces with a row-based update.
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from contracts.vocabulary import APP_RUNTIME_DATA_MODE
from helix_codex_app.db import record_node
from helix_codex_app.errors import PermissionDenied
from helix_codex_app.modules.calendar.repository import (
    CANCELLED,
    MAX_ATTENDEES,
    RECURRENCE_RULES,
    RESPONSES,
    CalendarRepository,
    Event,
    OnCallCoverage,
    OnCallShift,
    _parse,
)
from helix_codex_app.modules.notifications.service import MAX_PREVIEW, NotificationService
from helix_codex_app.security.accounts import Account

PROVENANCE_SOURCE = "helix_codex_app.calendar"
PROVENANCE_DATA_MODE = APP_RUNTIME_DATA_MODE
MANAGER_ROLES: tuple[str, ...] = ("owner", "manager")


class CalendarService:
    """Events, attendees, and RSVP, with the governance envelope."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.repo = CalendarRepository(conn)

    def create_event(
        self,
        account: Account,
        *,
        title: str,
        starts_at: str,
        ends_at: str,
        kind: str = "event",
        all_day: bool = False,
        location: str | None = None,
        room_id: str | None = None,
        recurrence_rule: str = "",
        attendee_account_ids: tuple[str, ...] = (),
    ) -> Event:
        if not title or not title.strip():
            raise ValueError("an event needs a title")
        self._validate_time(starts_at, ends_at)
        self._validate_recurrence(recurrence_rule)
        attendee_ids = tuple(dict.fromkeys(attendee_account_ids))
        if len(attendee_ids) > MAX_ATTENDEES:
            raise ValueError(f"an event can have at most {MAX_ATTENDEES} attendees")
        resolved = self.repo.resolve_attendees(account.tenant_id, attendee_ids)
        unknown = [account_id for account_id in attendee_ids if account_id not in resolved]
        if unknown:
            raise ValueError("unknown attendee account")
        event = self.repo.create_event(
            tenant_id=account.tenant_id,
            domain_id=account.domain_id,
            title=title.strip(),
            kind=kind,
            starts_at=starts_at,
            ends_at=ends_at,
            all_day=all_day,
            location=location,
            room_id=room_id,
            creator_account_id=account.account_id,
            recurrence_rule=recurrence_rule,
            attendee_account_ids=attendee_ids,
        )
        record_node(
            self.conn,
            tenant_id=account.tenant_id,
            client_id=account.client_id,
            domain_id=account.domain_id,
            correlation_id=f"event-{uuid.uuid4().hex}",
            classification="internal",
            nature="user_claim",
            created_by=account.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="event",
            body={
                "event_id": event.event_id,
                "title": event.title,
                "starts_at": event.starts_at,
                "ends_at": event.ends_at,
                "recurrence_rule": event.recurrence_rule,
                "status": event.status,
                "attendee_account_ids": [a.account_id for a in event.attendees],
            },
        )
        self._notify_new_attendees(account, event, attendee_ids)
        return event

    def get_event(self, account: Account, event_id: str) -> Event:
        return self.repo.get_event(event_id, account.tenant_id, account.account_id)

    def list_events(self, account: Account, from_at: str, to_at: str) -> list[Event]:
        return self.repo.list_events(
            tenant_id=account.tenant_id,
            account_id=account.account_id,
            from_at=from_at,
            to_at=to_at,
        )

    def update_event(
        self,
        account: Account,
        event_id: str,
        *,
        title: str | None = None,
        kind: str | None = None,
        starts_at: str | None = None,
        ends_at: str | None = None,
        all_day: bool | None = None,
        location: str | None = None,
        room_id: str | None = None,
        recurrence_rule: str | None = None,
        attendee_account_ids: tuple[str, ...] | None = None,
    ) -> Event:
        event = self.get_event(account, event_id)
        self._require_steward(account, event)
        changes: dict[str, object] = {}
        if title is not None:
            if not title.strip():
                raise ValueError("an event needs a title")
            changes["title"] = title.strip()
            title = title.strip()
        if starts_at is not None or ends_at is not None:
            next_start = starts_at if starts_at is not None else event.starts_at
            next_end = ends_at if ends_at is not None else event.ends_at
            self._validate_time(next_start, next_end)
            changes["starts_at"] = starts_at or event.starts_at
            changes["ends_at"] = ends_at or event.ends_at
        if recurrence_rule is not None:
            self._validate_recurrence(recurrence_rule)
            changes["recurrence_rule"] = recurrence_rule
        if all_day is not None:
            changes["all_day"] = all_day
        if location is not None:
            changes["location"] = location
        if room_id is not None:
            changes["room_id"] = room_id
        if kind is not None:
            changes["kind"] = kind
        attendee_ids: tuple[str, ...] = ()
        added: tuple[str, ...] = ()
        if attendee_account_ids is not None:
            attendee_ids = tuple(dict.fromkeys(attendee_account_ids))
            if len(attendee_ids) > MAX_ATTENDEES:
                raise ValueError(f"an event can have at most {MAX_ATTENDEES} attendees")
            resolved = self.repo.resolve_attendees(account.tenant_id, attendee_ids)
            unknown = [account_id for account_id in attendee_ids if account_id not in resolved]
            if unknown:
                raise ValueError("unknown attendee account")
            changes["attendee_account_ids"] = list(attendee_ids)
        event = self.repo.update_event(
            event_id,
            account.tenant_id,
            title=title,
            kind=kind,
            starts_at=starts_at,
            ends_at=ends_at,
            all_day=all_day,
            location=location,
            room_id=room_id,
            recurrence_rule=recurrence_rule,
        )
        if attendee_account_ids is not None:
            added = self.repo.set_attendees(event_id, account.tenant_id, attendee_ids)
        record_node(
            self.conn,
            tenant_id=account.tenant_id,
            client_id=account.client_id,
            domain_id=account.domain_id,
            correlation_id=f"event-{uuid.uuid4().hex}",
            classification="internal",
            nature="user_claim",
            created_by=account.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="event",
            body={
                "event_id": event.event_id,
                "title": event.title,
                "starts_at": event.starts_at,
                "ends_at": event.ends_at,
                "recurrence_rule": event.recurrence_rule,
                "status": event.status,
                "changed": {key: value for key, value in changes.items()},
            },
        )
        self._notify_new_attendees(account, event, added)
        return event

    def respond(self, account: Account, event_id: str, response: str) -> Event:
        if response not in RESPONSES:
            raise ValueError(f"response must be one of {', '.join(RESPONSES)}")
        event = self.repo.respond(event_id, account.tenant_id, account.account_id, response)
        record_node(
            self.conn,
            tenant_id=account.tenant_id,
            client_id=account.client_id,
            domain_id=account.domain_id,
            correlation_id=f"event-{uuid.uuid4().hex}",
            classification="internal",
            nature="user_claim",
            created_by=account.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="event_response",
            body={
                "event_id": event.event_id,
                "account_id": account.account_id,
                "response": response,
            },
        )
        return event

    def cancel_event(self, account: Account, event_id: str) -> Event:
        event = self.get_event(account, event_id)
        self._require_steward(account, event)
        event = self.repo.cancel_event(event_id, account.tenant_id)
        record_node(
            self.conn,
            tenant_id=account.tenant_id,
            client_id=account.client_id,
            domain_id=account.domain_id,
            correlation_id=f"event-{uuid.uuid4().hex}",
            classification="internal",
            nature="user_claim",
            created_by=account.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="event",
            body={
                "event_id": event.event_id,
                "title": event.title,
                "status": CANCELLED,
            },
        )
        return event

    def create_shift(
        self,
        account: Account,
        *,
        starts_at: str,
        ends_at: str,
        primary_account_id: str,
        backup_account_id: str,
    ) -> OnCallShift:
        """Roster one on-call window with a primary and a backup.

        Assigning a roster is a manager action: only owner and manager roles
        may create a shift. The primary and backup must be different accounts
        that already exist inside the tenant, and every write records one
        governed node so the roster assignment has an audit trail.
        """
        if account.role_id not in MANAGER_ROLES:
            raise PermissionDenied("only a manager may create an on-call shift")
        self._validate_time(starts_at, ends_at)
        if not primary_account_id.strip():
            raise ValueError("a shift needs a primary account")
        if not backup_account_id.strip():
            raise ValueError("a shift needs a backup account")
        if primary_account_id == backup_account_id:
            raise ValueError("primary and backup must be different accounts")
        resolved = self.repo.resolve_attendees(
            account.tenant_id, (primary_account_id, backup_account_id)
        )
        unknown = [
            account_id
            for account_id in (primary_account_id, backup_account_id)
            if account_id not in resolved
        ]
        if unknown:
            raise ValueError("unknown account")
        shift = self.repo.create_shift(
            tenant_id=account.tenant_id,
            domain_id=account.domain_id,
            starts_at=starts_at,
            ends_at=ends_at,
            primary_account_id=primary_account_id,
            backup_account_id=backup_account_id,
        )
        record_node(
            self.conn,
            tenant_id=account.tenant_id,
            client_id=account.client_id,
            domain_id=account.domain_id,
            correlation_id=f"shift-{uuid.uuid4().hex}",
            classification="internal",
            nature="user_claim",
            created_by=account.account_id,
            provenance_source=PROVENANCE_SOURCE,
            provenance_data_mode=PROVENANCE_DATA_MODE,
            kind="oncall_shift",
            body={
                "shift_id": shift.shift_id,
                "starts_at": shift.starts_at,
                "ends_at": shift.ends_at,
                "primary_account_id": shift.primary_account_id,
                "backup_account_id": shift.backup_account_id,
            },
        )
        return shift

    def list_shifts(self, account: Account, from_at: str, to_at: str) -> list[OnCallShift]:
        """All of the tenant's shifts overlapping [from_at, to_at)."""
        return self.repo.list_shifts(
            tenant_id=account.tenant_id,
            from_at=from_at,
            to_at=to_at,
        )

    def current_oncall(self, tenant_id: str, at: str) -> OnCallCoverage:
        """Who is on call at `at`, or a gap.

        A coverage question that has no rostered shift answers with
        OnCallCoverage(covered=False) — a gap, not an empty list, and never a
        fabricated roster.
        """
        shift = self.repo.get_current_shift(tenant_id, at)
        if shift is None:
            return OnCallCoverage(covered=False, shift=None, status="gap")
        return OnCallCoverage(covered=True, shift=shift, status="covered")

    def next_shifts(self, account: Account) -> list[OnCallShift]:
        """The account's upcoming shifts where it is primary or backup."""
        now = datetime.now(timezone.utc).isoformat()
        return self.repo.list_account_shifts(
            account_id=account.account_id,
            tenant_id=account.tenant_id,
            from_at=now,
        )

    def next_tenant_shift(self, tenant_id: str, after_at: str) -> OnCallShift | None:
        """The earliest shift in the tenant that starts after `after_at`."""
        return self.repo.get_next_shift(tenant_id, after_at)

    def _require_steward(self, account: Account, event: Event) -> None:
        if event.creator_account_id == account.account_id:
            return
        if account.role_id in MANAGER_ROLES:
            return
        raise PermissionDenied("only the creator or a manager may change this event")

    def _notify_new_attendees(
        self,
        account: Account,
        event: Event,
        attendee_ids: tuple[str, ...],
    ) -> None:
        for attendee_id in attendee_ids:
            if attendee_id == account.account_id:
                continue
            NotificationService(self.conn).create(
                account_id=attendee_id,
                tenant_id=account.tenant_id,
                client_id=account.client_id,
                domain_id=account.domain_id,
                kind="event_invite",
                title=f"Invited to event: {event.title}",
                body=f"{event.starts_at} (UTC)"[:MAX_PREVIEW],
                link="/app/calendar",
                created_by=account.account_id,
                correlation_id=f"event-notif-{uuid.uuid4().hex}",
            )

    def _validate_time(self, starts_at: str, ends_at: str) -> None:
        if not starts_at or not starts_at.strip() or not ends_at or not ends_at.strip():
            raise ValueError("a window needs a start and an end")
        try:
            start = _parse(starts_at)
            end = _parse(ends_at)
        except ValueError as exc:
            raise ValueError("starts_at and ends_at must be ISO timestamps") from exc
        if end <= start:
            raise ValueError("the window must end after it starts")

    def _validate_recurrence(self, recurrence_rule: str) -> None:
        if recurrence_rule not in RECURRENCE_RULES:
            raise ValueError(
                f"recurrence_rule must be one of {', '.join(RECURRENCE_RULES) or 'none'}"
            )
