"""Payment adapter (v1) — manual fee collection records only.

Explicit v1 boundary: NO payment gateway, NO payment instruments, NO
connector write path. A fee record is a manual bookkeeping entry (amount,
due date, optional paid-at, method note) stored in governed memory so it
carries provenance and the audit chain. Unpaid fees feed the renewal-flow
reminders and the MRR-adjacent outstanding view.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

from connectors.contracts import ConnectorContext

from ..ontology import Athlete, FeePayment

DATA_MODE = "simulated_realistic"


def monthly_recurring_revenue(athletes: Sequence[Athlete], programs: Sequence[Any]) -> float:
    """Design-point MRR: active athletes × their program's monthly fee."""
    fee_by_program = {p.program_id: p.monthly_fee for p in programs}
    return round(
        sum(
            fee_by_program.get(a.program_id, 0.0)
            for a in athletes
            if a.enrollment_status == "active"
        ),
        2,
    )


def outstanding_fees(fee_payments: Sequence[FeePayment]) -> Sequence[Dict[str, Any]]:
    return [
        {
            "payment_id": p.payment_id,
            "athlete_id": p.athlete_id,
            "family_id": p.family_id,
            "amount": p.amount,
            "due_date": p.due_date,
        }
        for p in fee_payments
        if p.paid_at is None
    ]


def record_manual_payment(
    mem,
    ctx: ConnectorContext,
    *,
    athlete_id: str,
    family_id: str,
    program_id: str,
    amount: float,
    currency: str,
    due_date: str,
    paid_at: Optional[str],
    method_note: str,
    as_of: str,
    actor: str = "academy-operator",
    role_id: str = "academy_admin",
    correlation_id: Optional[str] = None,
) -> str:
    """Record one manual fee entry in governed memory (kind=customer_context).

    The fee_record workflow category is committal: the runtime routes actual
    recording through the approval layer. This function is the write shape the
    runtime uses post-approval; it never touches an external system and stores
    no payment instrument (only a human-readable method note).
    """
    if amount < 0:
        raise ValueError("amount must be non-negative")
    corr = correlation_id or ctx.correlation_id or "academy-fee"
    rec = mem.add(
        kind="customer_context",
        nature="simulated_event",
        tenant_id=ctx.tenant_id,
        client_id=ctx.client_id,
        actor=actor,
        role_id=role_id,
        source="academy_billing",
        classification="client_confidential",
        timestamp=as_of,
        correlation_id=corr,
        confidence=1.0,
        evidence_refs=[f"fee:{athlete_id}:{due_date}"],
        data_mode=DATA_MODE,
        provenance={
            "correlation_id": corr,
            "data_mode": DATA_MODE,
            "basis": "manual_fee_record",
            "sources": [f"fee:{athlete_id}:{due_date}"],
        },
        body={
            "action": "record_manual_payment",
            "athlete_id": athlete_id,
            "family_id": family_id,
            "program_id": program_id,
            "amount": amount,
            "currency": currency,
            "due_date": due_date,
            "paid_at": paid_at,
            "method_note": method_note,
        },
    )
    return rec.record_id


def fee_status_overview(
    ctx: ConnectorContext,
    connectors: Dict[str, Any],
    athletes: Sequence[Athlete],
    programs: Sequence[Any],
) -> Dict[str, Any]:
    """Owner view: MRR, outstanding fees, collection status."""
    conn = connectors["academy_ops"]
    fees = conn.list_fee_payments(ctx)
    paid = [p for p in fees if p.paid_at is not None]
    return {
        "data_mode": DATA_MODE,
        "mrr": monthly_recurring_revenue(athletes, programs),
        "outstanding": outstanding_fees(fees),
        "paid_count": len(paid),
        "total_records": len(fees),
    }
