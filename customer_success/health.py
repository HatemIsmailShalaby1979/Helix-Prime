"""Deterministic, explainable customer-success account-health assessment."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from connectors.contracts import Account, ConnectorContext, EnrichmentResult, SupportTicket


@dataclass(frozen=True)
class AccountHealthAssessment:
    account_id: str
    tenant_id: str
    client_id: str
    score: float
    status: str
    risks: tuple[str, ...]
    recommended_actions: tuple[str, ...]
    evidence: tuple[Mapping[str, Any], ...]
    data_mode: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "tenant_id": self.tenant_id,
            "client_id": self.client_id,
            "score": self.score,
            "status": self.status,
            "risks": list(self.risks),
            "recommended_actions": list(self.recommended_actions),
            "evidence": [dict(item) for item in self.evidence],
            "data_mode": self.data_mode,
            "confidence": self.confidence,
        }


def assess_account_health(
    context: ConnectorContext,
    account: Account,
    tickets: Sequence[SupportTicket],
    enrichment: EnrichmentResult | None = None,
) -> AccountHealthAssessment:
    """Calculate a transparent health score; no model or external write involved."""
    if (account.tenant_id, account.client_id) != (context.tenant_id, context.client_id):
        raise PermissionError("account health scope mismatch")
    if enrichment and (enrichment.tenant_id, enrichment.client_id) != (context.tenant_id, context.client_id):
        raise PermissionError("enrichment scope mismatch")

    score = 100.0
    risks: list[str] = []
    actions: list[str] = []
    evidence: list[Mapping[str, Any]] = []

    for ticket in tickets:
        if (ticket.tenant_id, ticket.client_id) != (context.tenant_id, context.client_id):
            raise PermissionError("ticket scope mismatch")
        if ticket.sla_breached:
            score -= 25
            risks.append(f"sla_breach:{ticket.ticket_id}")
            actions.append("Prioritize SLA recovery and assign an accountable owner")
        if ticket.priority.lower() == "high" and ticket.status.lower() not in {"closed", "solved"}:
            score -= 10
            risks.append(f"open_high_priority_ticket:{ticket.ticket_id}")
            actions.append("Review open high-priority ticket in the next operating cycle")
        evidence.append({"provider": ticket.source.provider, "record_id": ticket.ticket_id, "type": "support_ticket", "source_version": ticket.source.input_version})

    if account.lifecycle_stage.lower() in {"onboarding", "adoption"}:
        actions.append("Schedule a customer-success adoption review")
    if enrichment and enrichment.fields.get("research_status") == "simulated":
        evidence.append({"provider": enrichment.source.provider, "record_id": account.account_id, "type": "enrichment", "source_version": enrichment.source.input_version})

    score = max(0.0, min(100.0, score))
    status = "at_risk" if score < 70 else "watch" if score < 85 else "healthy"
    confidence = 0.8 if tickets else 0.55
    return AccountHealthAssessment(
        account_id=account.account_id,
        tenant_id=context.tenant_id,
        client_id=context.client_id,
        score=score,
        status=status,
        risks=tuple(dict.fromkeys(risks)),
        recommended_actions=tuple(dict.fromkeys(actions)),
        evidence=tuple(evidence),
        data_mode=context.data_mode,
        confidence=confidence,
    )
