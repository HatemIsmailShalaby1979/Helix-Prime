from connectors.contracts import ConnectorContext
from connectors.fakes import build_demo_connectors


def test_demo_connectors_normalize_customer_success_data():
    context = ConnectorContext("tenant-1", "org-1", "client-1", correlation_id="corr-1")
    connectors = build_demo_connectors(context)
    account = connectors["salesforce"].list_accounts(context)[0]
    tickets = connectors["zendesk"].list_tickets(context, account.account_id)
    enrichment = connectors["clay"].enrich_account(context, account)
    assert account.source.provider == "Salesforce"
    assert tickets[0].source.provider == "Zendesk"
    assert enrichment.source.provider == "Clay"
    assert all(x.source.data_mode == "simulated_realistic" for x in (account, tickets[0], enrichment))


def test_connector_scope_isolation():
    context = ConnectorContext("tenant-1", "org-1", "client-1")
    other = ConnectorContext("tenant-2", "org-2", "client-2")
    connectors = build_demo_connectors(context)
    account = connectors["salesforce"].list_accounts(context)[0]
    assert connectors["salesforce"].list_accounts(other) == ()
    try:
        connectors["clay"].enrich_account(other, account)
    except PermissionError:
        pass
    else:
        raise AssertionError("cross-tenant enrichment must fail closed")


def test_external_writes_require_approval():
    context = ConnectorContext("tenant-1", "org-1", "client-1")
    capability = build_demo_connectors(context)["salesforce"].capabilities()[0]
    assert "account_update" in capability.writes
    assert capability.writes_require_approval is True
