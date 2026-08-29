import pytest

from connectors.contracts import ConnectorContext
from connectors.fakes import build_demo_connectors
from customer_success.health import assess_account_health


def test_account_health_combines_crm_support_and_enrichment_evidence():
    context = ConnectorContext("tenant-1", "org-1", "client-1", correlation_id="corr-1")
    connectors = build_demo_connectors(context)
    account = connectors["salesforce"].list_accounts(context)[0]
    tickets = connectors["zendesk"].list_tickets(context, account.account_id)
    enrichment = connectors["clay"].enrich_account(context, account)
    assessment = assess_account_health(context, account, tickets, enrichment)
    assert assessment.status == "at_risk"
    assert assessment.score == 65
    assert "sla_breach:ticket-001" in assessment.risks
    assert {item["provider"] for item in assessment.evidence} == {"Zendesk", "Clay"}
    assert assessment.data_mode == "simulated_realistic"


def test_account_health_fails_closed_on_cross_tenant_data():
    context = ConnectorContext("tenant-1", "org-1", "client-1")
    other = ConnectorContext("tenant-2", "org-2", "client-2")
    account = build_demo_connectors(context)["salesforce"].list_accounts(context)[0]
    with pytest.raises(PermissionError):
        assess_account_health(other, account, ())
