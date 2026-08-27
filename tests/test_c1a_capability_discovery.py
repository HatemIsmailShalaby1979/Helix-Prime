"""TDD for Codex C1a — capability-based discovery.

Tests per C1a ticket:
- agent capability discovery
- engine capability discovery
- role-to-capability ownership
- allowed/denied tool access
- unknown capability
- ambiguous capability
- legacy name-based compatibility
- deterministic routing
- no regression in current orchestrator behavior
"""
from __future__ import annotations

import pathlib

import pytest

from organization.role_catalog import load_role_catalog


# ── agent capability discovery ────────────────────────────────────────────

def test_agent_capability_discovery():
    from organization.capability_registry import get_agent_for_capability

    # wfm_forecast is owned by ops_gm per role-catalog.yaml
    assert get_agent_for_capability("wfm_forecast") == "ops_gm"
    assert get_agent_for_capability("talent_acquisition") == "hr_personnel_gm"
    assert get_agent_for_capability("policy_enforcement") == "compliance_quality_gm"
    assert get_agent_for_capability("anomaly_detection") == "fraud_gm"
    assert get_agent_for_capability("market_intelligence") == "marketing_gm"
    assert get_agent_for_capability("platform_ops") == "ict_gm"
    assert get_agent_for_capability("competency_analysis") == "ld_gm"
    assert get_agent_for_capability("strategic_oversight") == "sami"


def test_engine_capability_discovery():
    from organization.capability_registry import get_engine_for_capability

    # Engine capabilities per canonical engine registry (organization/capability-registry.yaml)
    assert get_engine_for_capability("erlang_c") == "WFM Forecasting"
    assert get_engine_for_capability("rta_adherence") == "RTA Command Center"
    assert get_engine_for_capability("churn_risk_scoring") == "CX Churn Sentinel"
    assert get_engine_for_capability("b2b_onboarding") == "B2B Onboarding"
    assert get_engine_for_capability("talent_acquisition_engine") == "Personnel Engine"
    assert get_engine_for_capability("sales_pipeline") == "CRM Engine"


# ── role-to-capability ownership ──────────────────────────────────────────

def test_role_to_capability_ownership():
    from organization.capability_registry import get_capabilities_for_role, is_capability_owned_by_role

    ops_caps = get_capabilities_for_role("ops_gm")
    assert "wfm_forecast" in ops_caps
    assert "rta_adherence" in ops_caps
    assert is_capability_owned_by_role("ops_gm", "wfm_forecast") is True
    assert is_capability_owned_by_role("ops_gm", "talent_acquisition") is False
    assert is_capability_owned_by_role("hr_personnel_gm", "workforce_planning") is True
    # marketing should not own ops capability
    assert is_capability_owned_by_role("marketing_gm", "wfm_forecast") is False


# ── allowed / denied tool access ──────────────────────────────────────────

def test_allowed_tool_access():
    from organization.capability_registry import is_tool_allowed

    # ops_gm is allowed wfm_engine per catalog
    assert is_tool_allowed("ops_gm", "wfm_engine") is True
    assert is_tool_allowed("ops_gm", "rta_engine") is True
    assert is_tool_allowed("hr_personnel_gm", "personnel_engine") is True
    assert is_tool_allowed("sami", "crm_engine_read") is True


def test_denied_tool_access():
    from organization.capability_registry import is_tool_allowed

    # marketing_gm is NOT allowed wfm_engine
    assert is_tool_allowed("marketing_gm", "wfm_engine") is False
    assert is_tool_allowed("marketing_gm", "personnel_engine") is False
    # ops_gm not allowed b2b_engine (sales_gm's tool)
    assert is_tool_allowed("ops_gm", "b2b_engine") is False
    # unknown role should fail closed
    with pytest.raises(ValueError, match="not found"):
        is_tool_allowed("unknown_gm", "wfm_engine")


# ── unknown capability ─────────────────────────────────────────────────────

def test_unknown_capability_fails_closed():
    from organization.capability_registry import get_agent_for_capability, get_engine_for_capability

    with pytest.raises(ValueError, match="unknown capability"):
        get_agent_for_capability("does_not_exist_capability_xyz")
    with pytest.raises(ValueError, match="unknown capability"):
        get_engine_for_capability("does_not_exist_engine_cap_xyz")


def test_unknown_capability_discovery_via_unified_api():
    from organization.capability_registry import discover

    with pytest.raises(ValueError, match="unknown capability"):
        discover("unknown_capability_123")


# ── ambiguous capability ──────────────────────────────────────────────────

def test_ambiguous_capability_fails_closed():
    from organization.capability_registry import discover
    from organization.role_catalog import validate_role_catalog

    # Build a synthetic catalog with duplicate capability to simulate ambiguous ownership
    catalog = load_role_catalog("organization/role-catalog.yaml")
    import copy

    data = {
        "schema_version": "1.0",
        "kpi_vocabulary": catalog["kpi_vocabulary"],
        "roles": copy.deepcopy(catalog["roles"]),
    }
    # Inject duplicate: make marketing_gm also claim wfm_forecast (owned by ops_gm)
    for r in data["roles"]:
        if r["id"] == "marketing_gm":
            r["owned_capabilities"].append("wfm_forecast")
    # The registry built from this synthetic catalog should detect ambiguous
    from organization.capability_registry import build_registry_from_catalog

    reg = build_registry_from_catalog(data)
    # discover should fail closed for ambiguous capability
    with pytest.raises(ValueError, match="ambiguous.*wfm_forecast"):
        reg.get_agent_for_capability("wfm_forecast")
    # Also test that the ambiguous capability is reported in registry's ambiguous set
    assert "wfm_forecast" in reg.ambiguous_agent_capabilities


# ── legacy name-based compatibility ───────────────────────────────────────

def test_legacy_name_based_compatibility():
    # Legacy orchestrator keyword routing must still work
    from orchestration.orchestrator import Orchestrator
    from organization.capability_registry import get_agent_for_capability
    from contracts.adapter import parse_legacy_calls

    o = Orchestrator()
    # legacy keyword routing
    assert "suby" in o._resolve_agents("service level is dropping")
    # legacy name mapping still valid
    assert get_agent_for_capability("wfm_forecast") == "ops_gm"
    # legacy call_agent text parsing still works and can be bridged to capability
    parsed = parse_legacy_calls('call_agent("PHILI", "What is headcount?")')
    assert parsed == [("PHILI", "What is headcount?")]
    # PHILI maps to hr_personnel_gm which owns workforce_planning
    assert get_agent_for_capability("workforce_planning") == "hr_personnel_gm"


def test_legacy_engine_paths_preserved():
    # Engine module paths must not be broken by new registry
    from pathlib import Path

    assert Path("engines/wfm/src/app_wfm.py").exists()
    assert Path("engines/rta/src/app.py").exists()
    # Engine capability registry should still point to same engine names
    from organization.capability_registry import get_engine_for_capability

    assert get_engine_for_capability("erlang_c") == "WFM Forecasting"


# ── deterministic routing ─────────────────────────────────────────────────

def test_deterministic_routing():
    from organization.capability_registry import get_agent_for_capability, discover
    from contracts.task import CorrelationContext
    from contracts.adapter import to_task_request, validate_request_against_catalog
    from organization.role_catalog import load_role_catalog

    catalog = load_role_catalog("organization/role-catalog.yaml")
    # Same capability request must always route to same owner
    first = get_agent_for_capability("wfm_forecast")
    second = get_agent_for_capability("wfm_forecast")
    assert first == second == "ops_gm"

    # discover via TaskRequest should be deterministic
    corr = CorrelationContext(correlation_id="corr_det", idempotency_key="idem_det", tenant_id="t", client_id="c", created_at="2026-08-27T18:00:00Z")
    from organization.capability_registry import route_task_request

    req1 = to_task_request(
        correlation=corr,
        requesting_actor="sami",
        requesting_role_id="sami",
        owning_role_id="ops_gm",
        capability="wfm_forecast",
        input_payload={},
    )
    # route should return same owner for same capability
    assert route_task_request(req1) == "ops_gm"
    # repeated call same
    assert route_task_request(req1) == "ops_gm"

    # Different capabilities route to different owners deterministically
    req2 = to_task_request(
        correlation=CorrelationContext(correlation_id="corr_det2", idempotency_key="idem_det2", tenant_id="t", client_id="c", created_at="2026-08-27T18:00:00Z"),
        requesting_actor="sami",
        requesting_role_id="sami",
        owning_role_id="hr_personnel_gm",
        capability="talent_acquisition",
        input_payload={},
    )
    assert route_task_request(req2) == "hr_personnel_gm"
    assert route_task_request(req2) != route_task_request(req1)


def test_deterministic_engine_routing():
    from organization.capability_registry import get_engine_for_capability

    # Engine routing also deterministic
    assert get_engine_for_capability("erlang_c") == get_engine_for_capability("erlang_c")
    assert get_engine_for_capability("sales_pipeline") == "CRM Engine"


# ── no regression in current orchestrator behavior ─────────────────────────

def test_no_regression_orchestrator_keyword_routing():
    from orchestration.orchestrator import Orchestrator

    o = Orchestrator()
    # These are the same checks as C0 smoke — must remain green
    assert o._resolve_agents("What is our hiring pipeline?")  # should still route (phili/sami)
    assert o._resolve_agents("service level is dropping") == ["suby"]
    assert o._resolve_agents("churn risk for customers") == ["suby"]
    assert o._resolve_agents("training competency gap") == ["wili"]
    assert o._resolve_agents("strategic market expansion") == ["sami"]
    assert set(o._resolve_agents("hello generic")) == {"sami", "suby", "phili"}


def test_no_regression_c1_contracts_still_green():
    # Spot-check that C1 contracts still validate and catalog loads
    from contracts.task import TaskRequest, CorrelationContext, EvidenceRef
    from organization.role_catalog import load_role_catalog

    catalog = load_role_catalog("organization/role-catalog.yaml")
    assert "sami" in catalog["roles_by_id"]
    c = CorrelationContext(correlation_id="corr_reg", idempotency_key="idem_reg", tenant_id="t", client_id="c", created_at="2026-08-27T18:00:00Z")
    req = TaskRequest(
        request_id="req_reg",
        correlation=c,
        requesting_actor="sami",
        owning_role_id="ops_gm",
        capability="wfm_forecast",
        input_payload={},
        requires_approval=False,
        status="proposed",
        created_at="2026-08-27T18:00:00Z",
        client_id="c",
    )
    assert req.owning_role_id == "ops_gm"
