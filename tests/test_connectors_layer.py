"""Provider-neutral connector layer — verification (read-only, credential-neutral).

Covers the Prompt-4 gate list:
* each connector tested independently (zendesk / salesforce / clay);
* malformed and unavailable providers;
* cross-tenant access denial;
* provenance preservation (correlation_id + data_mode + source refs);
* write capabilities cannot execute without approval;
* rate-limit behavior (fail closed);
* retry behavior (deterministic, retryable only);
* failure behavior (typed envelope, malformed input).
"""
from __future__ import annotations

import types

from connectors.contracts import (
    ConnectorContext,
    ConnectorResult,
    ConnectorStatus,
    FailureDetail,
    RateLimitPolicy,
    RetryPolicy,
)
from connectors.fakes import FakeConnector, build_demo_connectors
from connectors.registry import ConnectorRegistry, KNOWN_PROVIDERS


def _ctx(tenant="tenant-1", org="org-1", client="client-1", corr="corr-1"):
    return ConnectorContext(tenant, org, client, correlation_id=corr)


# ── each connector independently ─────────────────────────────────────────────

def test_salesforce_connector_independent():
    ctx = _ctx()
    sf = ConnectorRegistry().get_connector("salesforce", ctx)
    assert isinstance(sf, FakeConnector)
    assert sf.provider == "Salesforce"
    assert sf.status() == ConnectorStatus.HEALTHY
    accounts = sf.list_accounts(ctx)
    assert len(accounts) == 1
    assert accounts[0].source.provider == "Salesforce"
    assert accounts[0].tenant_id == ctx.tenant_id


def test_zendesk_connector_independent():
    ctx = _ctx()
    zd = ConnectorRegistry().get_connector("zendesk", ctx)
    assert zd.provider == "Zendesk"
    tickets = zd.list_tickets(ctx, "acct-001")
    assert len(tickets) == 1
    assert tickets[0].source.provider == "Zendesk"
    assert tickets[0].sla_breached is True


def test_clay_connector_independent():
    ctx = _ctx()
    clay = ConnectorRegistry().get_connector("clay", ctx)
    assert clay.provider == "Clay"
    sf = ConnectorRegistry().get_connector("salesforce", ctx)
    account = sf.list_accounts(ctx)[0]
    enrichment = clay.enrich_account(ctx, account)
    assert enrichment.source.provider == "Clay"
    assert 0.0 <= enrichment.confidence <= 1.0
    assert enrichment.fields.get("industry") == "contact-centre"


def test_capabilities_declare_classification_rate_limit_retry_approval():
    ctx = _ctx()
    for provider in KNOWN_PROVIDERS:
        cap = ConnectorRegistry().get_connector(provider, ctx).capabilities()[0]
        assert cap.data_classification == "client_confidential"
        assert cap.approval_required is True
        assert cap.writes_require_approval is True
        assert cap.writes == ("account_update",)
        assert isinstance(cap.rate_limit, RateLimitPolicy)
        assert isinstance(cap.retry, RetryPolicy)


# ── malformed + unavailable providers ───────────────────────────────────────

def test_malformed_provider_rejected():
    ctx = _ctx()
    for bad in ("bogus", "", "hubspot", "sales force"):
        try:
            ConnectorRegistry().get_connector(bad, ctx)
        except ValueError:
            pass
        else:
            raise AssertionError(f"malformed provider {bad!r} must be rejected")


def test_live_mode_not_activatable():
    try:
        ConnectorRegistry(mode="live")
    except ValueError:
        pass
    else:
        raise AssertionError("live mode must not be activatable yet (no credentials)")


def test_unavailable_provider_returns_error_result():
    ctx = _ctx()
    offline = FakeConnector("salesforce", "Salesforce", status=ConnectorStatus.DISCONNECTED)
    res = offline.list_accounts_result(ctx)
    assert res.status == "unavailable"
    assert res.error is not None and res.error.code == "connector_unavailable"
    assert res.error.retryable is False
    # revoked connector also refuses
    revoked = FakeConnector("salesforce", "Salesforce", status=ConnectorStatus.REVOKED)
    assert revoked.list_tickets_result(ctx, "acct-001").status == "unavailable"


# ── cross-tenant access denial ──────────────────────────────────────────────

def test_cross_tenant_access_denied():
    ctx = _ctx(tenant="tenant-1", client="client-1")
    other = _ctx(tenant="tenant-2", client="client-2")
    connectors = build_demo_connectors(ctx)
    # reads never leak: cross-tenant list returns empty (denial, not error)
    assert connectors["salesforce"].list_accounts(other) == ()
    # writes/enrichment fail closed with PermissionError
    account = connectors["salesforce"].list_accounts(ctx)[0]
    try:
        connectors["clay"].enrich_account(other, account)
    except PermissionError:
        pass
    else:
        raise AssertionError("cross-tenant enrichment must fail closed")
    # result-returning enrich path also fails closed
    res = connectors["clay"].enrich_account_result(other, account)
    assert res.status == "error" or res.data is None


# ── provenance preservation ─────────────────────────────────────────────────

def test_provenance_preserved_on_read():
    ctx = _ctx(corr="corr-prov")
    sf = ConnectorRegistry().get_connector("salesforce", ctx)
    res = sf.list_accounts_result(ctx)
    assert res.status == "ok"
    prov = res.provenance
    assert prov is not None
    assert prov.provider == "Salesforce"
    assert prov.connector_id == "salesforce"
    assert prov.correlation_id == "corr-prov"
    assert prov.data_mode == ctx.data_mode
    assert prov.record_count == len(res.data)


def test_provenance_preserved_on_enrichment():
    ctx = _ctx(corr="corr-enrich")
    connectors = build_demo_connectors(ctx)
    account = connectors["salesforce"].list_accounts(ctx)[0]
    res = connectors["clay"].enrich_account_result(ctx, account)
    assert res.status == "ok"
    assert res.provenance is not None
    assert res.provenance.correlation_id == "corr-enrich"
    assert len(res.provenance.source_refs) == 1
    assert res.provenance.source_refs[0].provider == "Clay"


# ── write capabilities cannot execute without approval ─────────────────────

def test_write_requires_approval_and_is_read_only():
    ctx = _ctx()
    sf = ConnectorRegistry().get_connector("salesforce", ctx)
    cap = sf.capabilities()[0]
    write_cap = cap.writes[0]  # "account_update"
    # No approval -> refused, never executed.
    no_approval = sf.request_write(ctx, write_cap, {"name": "x"})
    assert no_approval.executed is False
    assert no_approval.approval_required is True
    assert no_approval.reason == "approval_required"
    # Even with a valid cross-role approval, the read-only first version still
    # cannot execute a write (live adapter not activated).
    approval = types.SimpleNamespace(
        decision="approved", approver_actor="approver-bob", approver_role_id="sales_gm",
    )
    with_approval = sf.request_write(ctx, write_cap, {"name": "x"}, approval=approval)
    assert with_approval.executed is False
    assert with_approval.approval_required is True
    assert with_approval.reason == "read_only_first_version_disallows_writes"


def test_self_approval_is_rejected():
    ctx = _ctx()
    sf = ConnectorRegistry().get_connector("salesforce", ctx)
    cap = sf.capabilities()[0]
    write_cap = cap.writes[0]
    # approver == requester actor -> invalid (separation of duties)
    bad = types.SimpleNamespace(
        decision="approved", approver_actor=ctx.actor, approver_role_id="sales_gm",
    )
    res = sf.request_write(ctx, write_cap, {}, approval=bad)
    assert res.executed is False
    assert res.approval_required is True
    assert res.reason == "approval_required"


# ── rate-limit behavior (fail closed) ───────────────────────────────────────

def test_rate_limit_fail_closed():
    ctx = _ctx()
    account = build_demo_connectors(ctx)["salesforce"].list_accounts(ctx)[0]
    limited = FakeConnector(
        "salesforce", "Salesforce", accounts=[account],
        rate_limit=RateLimitPolicy(max_requests_per_window=2, on_exceed="fail_closed"),
    )
    assert limited.list_accounts_result(ctx).status == "ok"
    assert limited.list_accounts_result(ctx).status == "ok"
    third = limited.list_accounts_result(ctx)
    assert third.status == "rate_limited"
    assert third.error is not None and third.error.retryable is True
    # no data leaked despite the limit
    assert third.data is None


# ── retry behavior (deterministic, retryable only) ──────────────────────────

def test_retry_succeeds_after_transient_failures():
    ctx = _ctx()
    sf = ConnectorRegistry().get_connector("salesforce", ctx)
    state = {"n": 0}

    def flaky() -> ConnectorResult:
        state["n"] += 1
        if state["n"] < 3:
            return ConnectorResult(
                status="error",
                error=FailureDetail("transient", "temporary outage", retryable=True),
                correlation_id=ctx.correlation_id,
            )
        return ConnectorResult(status="ok", data=("recovered",), correlation_id=ctx.correlation_id)

    res = sf.with_retry(flaky, ctx)
    assert res.status == "ok"
    assert state["n"] == 3  # retried until success


def test_retry_does_not_retry_non_retryable():
    ctx = _ctx()
    sf = ConnectorRegistry().get_connector("salesforce", ctx)
    calls = {"n": 0}

    def fatal() -> ConnectorResult:
        calls["n"] += 1
        return ConnectorResult(
            status="error",
            error=FailureDetail("auth", "forbidden", retryable=False),
            correlation_id=ctx.correlation_id,
        )

    res = sf.with_retry(fatal, ctx)
    assert res.status == "error"
    assert res.error.code == "auth"
    assert calls["n"] == 1  # not retried


# ── failure behavior (typed envelope, malformed input) ──────────────────────

def test_failure_behavior_malformed_input():
    ctx = _ctx()
    zd = ConnectorRegistry().get_connector("zendesk", ctx)
    empty = zd.list_tickets_result(ctx, "")
    assert empty.status == "error"
    assert empty.error is not None and empty.error.code == "invalid_input"
    nonstr = zd.list_tickets_result(ctx, 123)  # type: ignore[arg-type]
    assert nonstr.status == "error"
    assert nonstr.data is None


def test_missing_data_returns_empty_safely():
    # "Missing data" (valid request, no matching records) must return an empty
    # result, never raise or leak another tenant's data.
    ctx = _ctx()
    connectors = build_demo_connectors(ctx)
    assert connectors["zendesk"].list_tickets(ctx, "acct-does-not-exist") == ()
    assert connectors["zendesk"].list_tickets_result(ctx, "acct-does-not-exist").data == ()
    # A tenant with no accounts of its own sees nothing (denial, not error).
    empty_ctx = _ctx(tenant="tenant-with-no-data", client="c-x")
    assert connectors["salesforce"].list_accounts(empty_ctx) == ()
