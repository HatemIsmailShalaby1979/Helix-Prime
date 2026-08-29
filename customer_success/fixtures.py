"""Deterministic fixtures for the customer-success wedge (Prompt 5).

Every fixture returns an :class:`AccountContextBundle` with explicit `as_of` and
`data_mode` so diagnoses are reproducible and the data provenance is visible.
Four archetypes are provided: healthy, at-risk, unknown, contradictory. Each can
be labelled historical (`historical_consented`) or simulated (`simulated_realistic`).
"""
from __future__ import annotations

import datetime as _dt
from typing import Optional, Sequence

from connectors.contracts import (
    Account,
    ConnectorContext,
    CustomerSignal,
    EnrichmentResult,
    SourceRef,
    SupportTicket,
)
from customer_success.wedge import AccountContextBundle

DEFAULT_AS_OF = "2026-08-29T12:00:00Z"
STALE_DAYS = 90


def _parse(ts: str) -> _dt.datetime:
    return _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _offset(as_of: str, days: int) -> str:
    d = _parse(as_of) - _dt.timedelta(days=days)
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def _src(provider: str, record_id: str, observed_at: str, version: str, data_mode: str) -> SourceRef:
    return SourceRef(provider, record_id, observed_at, version, data_mode)


def make_bundle(
    ctx: ConnectorContext,
    data_mode: str,
    as_of: str = DEFAULT_AS_OF,
    *,
    account: Optional[Account] = None,
    tickets: Sequence[SupportTicket] = (),
    enrichment: Optional[EnrichmentResult] = None,
    signals: Sequence[CustomerSignal] = (),
) -> AccountContextBundle:
    return AccountContextBundle(
        context=ctx,
        account=account,
        tickets=list(tickets),
        enrichment=enrichment,
        signals=list(signals),
        data_mode=data_mode,
        as_of=as_of,
    )


def _account(ctx, account_id, lifecycle, observed_at, data_mode, version="sf-v1", attributes=None):
    return Account(
        account_id, f"Account {account_id}", lifecycle, "owner-demo",
        _src("Salesforce", account_id, observed_at, version, data_mode),
        ctx.tenant_id, ctx.client_id, attributes or {},
    )


def _ticket(ctx, ticket_id, account_id, observed_at, data_mode, *, sla_breached=False, priority="low", status="solved"):
    return SupportTicket(
        ticket_id, account_id, f"Ticket {ticket_id}", status, priority, sla_breached,
        observed_at, _src("Zendesk", ticket_id, observed_at, "zd-v1", data_mode),
        ctx.tenant_id, ctx.client_id,
    )


def _enrichment(ctx, account_id, observed_at, data_mode, fields):
    return EnrichmentResult(
        account_id, fields, 0.9,
        _src("Clay", account_id, observed_at, "clay-v1", data_mode),
        ctx.tenant_id, ctx.client_id,
    )


def _signal(ctx, signal_id, account_id, observed_at, data_mode, signal_type, value):
    return CustomerSignal(
        signal_id, account_id, signal_type, float(value), observed_at,
        _src("OperationalTelemetry", signal_id, observed_at, "ops-v1", data_mode),
        ctx.tenant_id, ctx.client_id,
    )


def healthy_account(ctx, data_mode="simulated_realistic", as_of=DEFAULT_AS_OF, stale=False):
    a = _account(ctx, "acct-healthy", "renewal", _offset(as_of, 2), data_mode)
    t = _ticket(ctx, "tk-h1", "acct-healthy", _offset(as_of, 3 if not stale else STALE_DAYS), data_mode)
    e = _enrichment(ctx, "acct-healthy", _offset(as_of, 2 if not stale else STALE_DAYS), data_mode,
                    {"industry": "contact-centre", "employee_band": "51-200", "research_status": "verified"})
    s = _signal(ctx, "sig-h1", "acct-healthy", _offset(as_of, 1), data_mode, "product_usage", 0.2)
    return make_bundle(ctx, data_mode, as_of, account=a, tickets=[t], enrichment=e, signals=[s])


def at_risk_account(ctx, data_mode="simulated_realistic", as_of=DEFAULT_AS_OF, stale=False):
    a = _account(ctx, "acct-risk", "adoption", _offset(as_of, 2), data_mode)
    t = _ticket(ctx, "tk-r1", "acct-risk", _offset(as_of, 1 if not stale else STALE_DAYS), data_mode,
                sla_breached=True, priority="high", status="open")
    e = _enrichment(ctx, "acct-risk", _offset(as_of, 2 if not stale else STALE_DAYS), data_mode,
                    {"industry": "contact-centre", "employee_band": "51-200", "research_status": "simulated"})
    s = _signal(ctx, "sig-r1", "acct-risk", _offset(as_of, 1), data_mode, "product_usage", -0.4)
    return make_bundle(ctx, data_mode, as_of, account=a, tickets=[t], enrichment=e, signals=[s])


def unknown_account(ctx, data_mode="simulated_realistic", as_of=DEFAULT_AS_OF):
    # Account present but no tickets, enrichment, or signals -> insufficient data.
    a = _account(ctx, "acct-unknown", "onboarding", _offset(as_of, 1), data_mode)
    return make_bundle(ctx, data_mode, as_of, account=a)


def contradictory_account(ctx, data_mode="simulated_realistic", as_of=DEFAULT_AS_OF, stale=False):
    # Account attribute `industry=finance` conflicts with Clay enrichment `industry=contact-centre`.
    a = _account(ctx, "acct-conflict", "adoption", _offset(as_of, 2), data_mode,
                 attributes={"industry": "finance"})
    t = _ticket(ctx, "tk-c1", "acct-conflict", _offset(as_of, 1 if not stale else STALE_DAYS), data_mode,
                sla_breached=False, priority="low", status="open")
    e = _enrichment(ctx, "acct-conflict", _offset(as_of, 2 if not stale else STALE_DAYS), data_mode,
                    {"industry": "contact-centre", "employee_band": "51-200", "research_status": "simulated"})
    return make_bundle(ctx, data_mode, as_of, account=a, tickets=[t], enrichment=e)
