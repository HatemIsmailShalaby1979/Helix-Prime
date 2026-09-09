"""Sports-academy business ontology (v1).

Frozen, source-attributed records. Each carries tenant/client scope and a
:class:`connectors.contracts.SourceRef` so synthetic data is never mistaken for
live external data. The ontology is intentionally small (one location).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from connectors.contracts import SourceRef


@dataclass(frozen=True)
class Family:
    family_id: str
    primary_contact_name: str
    phone: str
    email: str
    tenant_id: str
    client_id: str
    source: SourceRef


@dataclass(frozen=True)
class Athlete:
    athlete_id: str
    name: str
    birth_date: str  # ISO date
    program_id: str
    family_id: str
    enrollment_status: str  # inquiry | trial | enrolled | active | renewed | churned
    tenant_id: str
    client_id: str
    source: SourceRef


@dataclass(frozen=True)
class Coach:
    coach_id: str
    name: str
    tenant_id: str
    client_id: str
    source: SourceRef


@dataclass(frozen=True)
class Program:
    program_id: str
    name: str  # e.g. "U12 Football", "U15 Basketball"
    monthly_fee: float
    tenant_id: str
    client_id: str
    source: SourceRef


@dataclass(frozen=True)
class Session:
    session_id: str
    date: str  # ISO date
    start: str  # HH:MM
    end: str  # HH:MM
    program_id: str
    coach_id: str
    facility_slot_id: str
    roster: Tuple[str, ...]  # athlete ids expected to attend
    tenant_id: str
    client_id: str
    source: SourceRef


@dataclass(frozen=True)
class CheckIn:
    checkin_id: str
    athlete_id: str
    session_id: str
    check_in_at: str  # ISO timestamp
    check_out_at: Optional[str] = None  # ISO timestamp, None while still on site
    tenant_id: str = ""
    client_id: str = ""
    source: Optional[SourceRef] = None


@dataclass(frozen=True)
class FacilitySlot:
    slot_id: str
    date: str
    start: str
    end: str
    surface: str  # e.g. "court-1" | "field-a"
    booked_by_session_id: Optional[str]  # None = available
    tenant_id: str
    client_id: str
    source: SourceRef


@dataclass(frozen=True)
class FeePayment:
    payment_id: str
    athlete_id: str
    family_id: str
    program_id: str
    amount: float
    currency: str
    due_date: str
    paid_at: Optional[str]  # None = outstanding
    method_note: str  # manual record only: "cash", "bank transfer", etc.
    tenant_id: str
    client_id: str
    source: SourceRef


@dataclass(frozen=True)
class EnrollmentRecord:
    enrollment_id: str
    athlete_id: str
    stage: str  # inquiry | trial | enrollment | payment | renewed | churned
    recorded_at: str
    note: str
    tenant_id: str
    client_id: str
    source: SourceRef
