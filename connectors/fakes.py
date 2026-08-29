"""Deterministic Salesforce, Zendesk, and Clay fakes for local proof.

These fakes are credential-neutral and read-only by construction: they return
synthetic-but-realistic records, never contact a live provider, and never
execute writes. They subclass :class:`connectors.base.BaseConnector` so they
inherit the governed scope / rate-limit / retry / provenance / write-gating
behavior.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .base import BaseConnector
from .contracts import (
    Account,
    ConnectorCapability,
    ConnectorContext,
    ConnectorStatus,
    CustomerSignal,
    EnrichmentResult,
    SourceRef,
    SupportTicket,
    _version,
)


class FakeConnector(BaseConnector):
    def __init__(
        self,
        connector_id: str,
        provider: str,
        accounts: Sequence[Account] = (),
        tickets: Mapping[str, Sequence[SupportTicket]] | None = None,
        enrichment: Mapping[str, Mapping[str, Any]] | None = None,
        statuses: Mapping[str, str] | None = None,
        rate_limit=None,
        retry=None,
        status: ConnectorStatus = ConnectorStatus.HEALTHY,
    ) -> None:
        super().__init__(connector_id, provider, rate_limit=rate_limit, retry=retry, status=status)
        self._accounts = list(accounts)
        self._tickets = dict(tickets or {})
        self._enrichment = dict(enrichment or {})

    def capabilities(self) -> Sequence[ConnectorCapability]:
        return (ConnectorCapability(
            connector_id=self.connector_id,
            provider=self.provider,
            capability_id=f"{self.provider.lower()}_customer_read",
            reads=("account", "ticket", "customer_signal"),
            writes=("account_update",),
            risk_class="client_confidential",
            writes_require_approval=True,
            data_classification="client_confidential",
            approval_required=True,
        ),)

    # ----- protected fetchers (scope-filtered; never leak cross-tenant data) --
    def _fetch_accounts(self, context: ConnectorContext) -> Sequence[Account]:
        return [
            a for a in self._accounts
            if a.tenant_id == context.tenant_id and a.client_id == context.client_id
        ]

    def _fetch_tickets(self, context: ConnectorContext, account_id: str) -> Sequence[SupportTicket]:
        return [
            t for t in self._tickets.get(account_id, ())
            if t.tenant_id == context.tenant_id and t.client_id == context.client_id
        ]

    def _fetch_enrichment(self, context: ConnectorContext, account: Account) -> EnrichmentResult:
        self._assert_scope(context, account.tenant_id, account.client_id)
        fields = self._enrichment.get(account.account_id, {})
        source = SourceRef(
            self.provider,
            account.account_id,
            account.source.observed_at,
            _version(fields),
            context.data_mode,
        )
        return EnrichmentResult(
            account.account_id, fields, 0.85, source, context.tenant_id, context.client_id,
        )


def build_demo_connectors(context: ConnectorContext) -> dict[str, FakeConnector]:
    account_source = SourceRef("Salesforce", "acct-001", "2026-08-29T00:00:00Z", "sf-demo-v1", context.data_mode)
    account = Account(
        "acct-001", "Demo Account", "adoption", "owner-demo",
        account_source, context.tenant_id, context.client_id,
    )
    ticket_source = SourceRef("Zendesk", "ticket-001", "2026-08-29T00:05:00Z", "zd-demo-v1", context.data_mode)
    ticket = SupportTicket(
        "ticket-001", "acct-001", "Priority onboarding issue", "open", "high", True,
        "2026-08-29T00:05:00Z", ticket_source, context.tenant_id, context.client_id,
    )
    common = {"acct-001": [ticket]}
    return {
        "salesforce": FakeConnector("salesforce", "Salesforce", accounts=[account]),
        "zendesk": FakeConnector("zendesk", "Zendesk", tickets=common),
        "clay": FakeConnector(
            "clay", "Clay",
            enrichment={"acct-001": {"employee_band": "51-200", "industry": "contact-centre", "research_status": "simulated"}},
        ),
    }
