"""Restaurant business ontology (Prompt 11).

Frozen, source-attributed records. Each carries tenant/client scope and a
:class:`connectors.contracts.SourceRef` so synthetic data is never mistaken for
live external data. The ontology is intentionally small (one location).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from connectors.contracts import SourceRef


@dataclass(frozen=True)
class Employee:
    employee_id: str
    name: str
    role: str  # cook | server | host | dishwasher
    can_work: Tuple[str, ...]  # shift types this employee can cover
    tenant_id: str
    client_id: str
    source: SourceRef


@dataclass(frozen=True)
class Shift:
    shift_id: str
    date: str
    start: str
    end: str
    shift_type: str  # e.g. "lunch" | "dinner"
    required_headcount: int
    assigned: Tuple[str, ...]  # employee ids
    tenant_id: str
    client_id: str
    source: SourceRef


@dataclass(frozen=True)
class InventoryItem:
    item_id: str
    name: str
    category: str  # produce | dry_goods | dairy | protein
    on_hand: float
    unit: str
    par_level: float  # reorder threshold
    supplier_id: str
    tenant_id: str
    client_id: str
    source: SourceRef


@dataclass(frozen=True)
class Supplier:
    supplier_id: str
    name: str
    lead_time_days: int
    reliability: float  # 0.0-1.0
    tenant_id: str
    client_id: str
    source: SourceRef


@dataclass(frozen=True)
class Complaint:
    complaint_id: str
    channel: str  # dine_in | phone | online
    severity: str  # low | medium | high
    category: str  # food | service | delay
    opened_at: str
    sla_due_at: str
    status: str  # open | in_progress | resolved
    tenant_id: str
    client_id: str
    source: SourceRef


@dataclass(frozen=True)
class DailySummary:
    date: str
    covers: int
    revenue: float
    complaints_open: int
    shifts_filled: int
    shifts_required: int
    tenant_id: str
    client_id: str
    source: SourceRef
