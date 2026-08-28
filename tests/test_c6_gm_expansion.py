"""TDD for Codex C6 — GM Expansion (5 new governed GMs + 2 extended).

Tests cover:
- All five new GM role definitions in catalog
- Role catalog validation
- Capability registration (agent capabilities from role catalog)
- Role-to-capability ownership
- Allowed and denied tools
- Allowed and denied peer calls
- Approval limits and SOD rules
- Tenant/client isolation
- Fail-closed unknown capability
- Fail-closed unauthorized action
- Existing four-agent regression
- Existing C0–C5 regression
- Ollama-unavailable behavior
- Catalog-only GMs not claiming unavailable execution tools
"""
from __future__ import annotations

import sys
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest

from organization.role_catalog import load_role_catalog
from organization.capability_registry import (
    get_agent_for_capability,
    get_capabilities_for_role,
    is_capability_owned_by_role,
    is_tool_allowed,
    discover,
    get_default_registry,
    validate_mirror_drift,
)
from app.command_center.agents.base_agent import AgentRegistry
from contracts.task import CorrelationContext, TaskRequest
from control_plane.engine import Engine
from control_plane.store import Store
from engines.registry import register_all


# ── Role Catalog Tests ──

def test_all_nine_gms_in_catalog():
    """All 9 GMs (4 existing + 5 new) are present in role catalog."""
    catalog = load_role_catalog("organization/role-catalog.yaml")
    role_ids = {r["id"] for r in catalog["roles"]}
    expected = {
        "sami", "ops_gm", "hr_personnel_gm", "ld_gm",  # existing
        "compliance_quality_gm", "fraud_gm", "marketing_gm",
        "sales_gm", "ict_gm"  # new
    }
    assert role_ids == expected, f"Missing roles: {expected - role_ids}"


def test_new_gms_are_catalog_only():
    """New GMs have implementation_status=catalog_only until functional."""
    catalog = load_role_catalog("organization/role-catalog.yaml")
    for role in catalog["roles"]:
        if role["id"] in {"compliance_quality_gm", "fraud_gm", "marketing_gm", "sales_gm", "ict_gm"}:
            assert role["implementation_status"] == "catalog_only", \
                f"{role['id']} should be catalog_only, got {role['implementation_status']}"
            assert role["maps_to_agent"] is None
        elif role["id"] in {"sami", "ops_gm", "hr_personnel_gm", "ld_gm"}:
            assert role["implementation_status"] == "functional_agent"
            assert role["maps_to_agent"] is not None


def test_new_gm_capabilities_registered():
    """Each new GM's owned capabilities are discoverable via capability registry."""
    registry = get_default_registry()
    expected_caps = {
        "compliance_quality_gm": [
            "policy_enforcement", "qa_sampling", "risk_controls",
            "evidence_pack", "escalation_review", "calibration", "corrective_actions"
        ],
        "fraud_gm": [
            "anomaly_detection", "leakage_analysis", "fraud_investigation",
            "revenue_assurance", "abuse_detection"
        ],
        "marketing_gm": [
            "market_intelligence", "campaign_management", "positioning",
            "demand_generation", "content_review", "attribution"
        ],
        "sales_gm": [
            "pipeline_management", "deal_qualification", "proposal_generation",
            "revenue_execution", "crm_operations", "b2b_handoff",
            "sales_pipeline", "customer_support"
        ],
        "ict_gm": [
            "platform_ops", "integration_management", "security",
            "reliability", "release_operations", "incident_management"
        ],
    }
    for role_id, caps in expected_caps.items():
        role_caps = registry.get_capabilities_for_role(role_id)
        for cap in caps:
            assert cap in role_caps, f"Capability {cap!r} missing from {role_id}"
            assert registry.is_capability_owned_by_role(role_id, cap)
            owner = get_agent_for_capability(cap)
            assert owner == role_id, f"Capability {cap!r} owned by {owner!r}, expected {role_id!r}"


def test_new_gm_tools_allowed():
    """New GMs have allowed_tools and tool checks work."""
    registry = get_default_registry()
    expected_tools = {
        "compliance_quality_gm": ["policy_engine", "audit_log", "evidence_store", "ollama", "cognitive_log", "all_engines_read"],
        "fraud_gm": ["crm_engine_read", "b2b_engine_read", "cx_engine_read", "anomaly_engine", "ollama", "cognitive_log"],
        "marketing_gm": ["crm_engine_read", "approved_content", "ollama", "cognitive_log"],
        "sales_gm": ["crm_engine", "b2b_engine", "ollama", "cognitive_log"],
        "ict_gm": ["platform_runtime", "integration_hub", "deployment_pipeline", "observability", "ollama", "cognitive_log"],
    }
    for role_id, tools in expected_tools.items():
        role_tools = registry.role_to_tools[role_id]
        for tool in tools:
            assert tool in role_tools, f"Tool {tool!r} missing from {role_id}"
            assert is_tool_allowed(role_id, tool), f"Tool {tool!r} not allowed for {role_id}"
        # Test denied tool
        denied_tool = "wfm_engine"
        assert not is_tool_allowed(role_id, denied_tool), f"Tool {denied_tool!r} should be denied for {role_id}"


def test_new_gm_peer_calls():
    """New GMs have allowed_peer_calls and SOD restrictions."""
    catalog = load_role_catalog("organization/role-catalog.yaml")
    roles_by_id = catalog["roles_by_id"]

    # Compliance can call all GMs
    compliance_peers = roles_by_id["compliance_quality_gm"]["allowed_peer_calls"]
    for peer in ["ops_gm", "hr_personnel_gm", "sales_gm", "fraud_gm", "ld_gm", "marketing_gm", "ict_gm", "sami"]:
        assert peer in compliance_peers, f"Compliance should be able to call {peer}"

    # Fraud calls compliance, sales, ops, sami
    fraud_peers = roles_by_id["fraud_gm"]["allowed_peer_calls"]
    for peer in ["compliance_quality_gm", "sales_gm", "ops_gm", "sami"]:
        assert peer in fraud_peers, f"Fraud should be able to call {peer}"

    # Marketing calls sales, compliance, sami
    marketing_peers = roles_by_id["marketing_gm"]["allowed_peer_calls"]
    for peer in ["sales_gm", "sami", "compliance_quality_gm"]:
        assert peer in marketing_peers, f"Marketing should be able to call {peer}"

    # Sales calls marketing, ops, compliance, fraud, sami
    sales_peers = roles_by_id["sales_gm"]["allowed_peer_calls"]
    for peer in ["marketing_gm", "ops_gm", "sami", "compliance_quality_gm", "fraud_gm"]:
        assert peer in sales_peers, f"Sales should be able to call {peer}"

    # ICT calls compliance, sami, ops
    ict_peers = roles_by_id["ict_gm"]["allowed_peer_calls"]
    for peer in ["compliance_quality_gm", "sami", "ops_gm"]:
        assert peer in ict_peers, f"ICT should be able to call {peer}"


def test_approval_limits():
    """New GMs have approval_limits with correct tiers."""
    catalog = load_role_catalog("organization/role-catalog.yaml")
    roles_by_id = catalog["roles_by_id"]

    assert roles_by_id["compliance_quality_gm"]["approval_limits"]["tier"] == "compliance"
    assert roles_by_id["fraud_gm"]["approval_limits"]["tier"] == "financial"
    assert roles_by_id["marketing_gm"]["approval_limits"]["tier"] == "standard"
    assert roles_by_id["sales_gm"]["approval_limits"]["tier"] == "financial"
    assert roles_by_id["ict_gm"]["approval_limits"]["tier"] == "platform"

    # Compliance can approve all tiers
    compliance_approval = roles_by_id["compliance_quality_gm"]["approval_limits"]["can_approve"]
    for tier in ["standard", "financial", "personnel", "compliance", "external_communication", "irreversible"]:
        assert tier in compliance_approval

    # Others cannot approve compliance/irreversible
    for role_id in ["fraud_gm", "marketing_gm", "sales_gm", "ict_gm"]:
        approval = roles_by_id[role_id]["approval_limits"]["can_approve"]
        assert "compliance" not in approval
        assert "irreversible" not in approval


def test_sod_rules():
    """New GMs have SOD rules: cannot_approve_own_actions, must_be_reviewed_by."""
    catalog = load_role_catalog("organization/role-catalog.yaml")
    roles_by_id = catalog["roles_by_id"]

    for role_id in ["compliance_quality_gm", "fraud_gm", "marketing_gm", "sales_gm", "ict_gm"]:
        sod = roles_by_id[role_id]["segregation_of_duties"]
        assert sod["cannot_approve_own_actions"] is True
        assert "compliance_quality_gm" in sod["must_be_reviewed_by"] or role_id == "compliance_quality_gm"

    # Compliance cannot approve own actions, must be reviewed by SAMI
    compliance_sod = roles_by_id["compliance_quality_gm"]["segregation_of_duties"]
    assert compliance_sod["cannot_approve_own_actions"] is True
    assert compliance_sod["must_be_reviewed_by"] == []  # empty means SAMI escalation


def test_capability_registry_mirror_drift():
    """Canonical capability registry mirrors match."""
    validate_mirror_drift()  # Should not raise


# ── Agent Registry Tests ──

def test_all_nine_agents_registered():
    """All 9 agents (4 existing + 5 new) are registered in AgentRegistry."""
    agents = AgentRegistry.list_available()
    expected = {"SAMI", "SUBY", "PHILI", "WILI", "COMPLIANCE", "FRAUD", "MARKETING", "SALES", "ICT"}
    assert set(agents) == expected


def test_new_agents_have_correct_roles():
    """New agents have correct role names."""
    for name, expected_role in [
        ("COMPLIANCE", "Compliance & Quality GM"),
        ("FRAUD", "Fraud Analysis & Revenue Assurance GM"),
        ("MARKETING", "Marketing GM"),
        ("SALES", "Sales GM"),
        ("ICT", "ICT GM"),
    ]:
        agent = AgentRegistry.get_agent(name)
        assert agent is not None, f"Agent {name} not registered"
        assert agent.role == expected_role, f"{name} role mismatch: {agent.role!r} != {expected_role!r}"


def test_new_agents_have_system_prompts():
    """New agents have non-empty system prompts."""
    for name in ["COMPLIANCE", "FRAUD", "MARKETING", "SALES", "ICT"]:
        agent = AgentRegistry.get_agent(name)
        assert agent.system_prompt, f"Agent {name} missing system_prompt"
        assert len(agent.system_prompt) > 100, f"Agent {name} system_prompt too short"


# ── Authorization/SOD Regression Tests ──

def test_fail_closed_unknown_capability():
    """Unknown capability fails closed in authorization."""
    from security.identity import Identity
    from security.policy import AuthorizationRequest, authorize

    ident = Identity(actor="suby", actor_type="agent", tenant_id="t1", client_id="c1", role_id="ops_gm")
    req = AuthorizationRequest(identity=ident, capability="unknown_capability_xyz", tool="wfm_engine")
    decision = authorize(req)
    assert decision.allowed is False
    assert decision.code == "unknown_capability"


def test_fail_closed_unauthorized_role():
    """Unauthorized role fails closed."""
    from security.identity import Identity
    from security.policy import AuthorizationRequest, authorize

    ident = Identity(actor="marketing_user", actor_type="agent", tenant_id="t1", client_id="c1", role_id="marketing_gm")
    req = AuthorizationRequest(identity=ident, capability="wfm_forecast", tool="wfm_engine", owning_role_id="marketing_gm")
    decision = authorize(req)
    assert decision.allowed is False
    assert decision.code == "unauthorized_role"


def test_tenant_isolation():
    """Tenant isolation enforced in authorization."""
    from security.identity import Identity
    from security.policy import AuthorizationRequest, authorize

    ident = Identity(actor="suby", actor_type="agent", tenant_id="tenant_a", client_id="client_a", role_id="ops_gm")
    req = AuthorizationRequest(identity=ident, capability="wfm_forecast", tool="wfm_engine", owning_role_id="ops_gm", target_tenant_id="tenant_b")
    decision = authorize(req)
    assert decision.allowed is False
    assert decision.code == "tenant_isolation"


def test_existing_four_agent_regression():
    """Existing four agents still work."""
    for name in ["SAMI", "SUBY", "PHILI", "WILI"]:
        agent = AgentRegistry.get_agent(name)
        assert agent is not None, f"Existing agent {name} missing"
        # Verify they can process a simple request (no Ollama needed - will get LLM error but that's ok)
        result = agent.process_request("test")
        assert isinstance(result, str)


def test_existing_c0_c5_regression():
    """Run C5 vertical slice to ensure no regression."""
    import tempfile
    from tests.fixtures.c5.fixtures import (
        TENANT_ID, CLIENT_ID, ACTOR_SUBY, ACTOR_SAMI, ACTOR_PHILI, ACTOR_WILI,
        ACTOR_COMPLIANCE, ACTOR_SALES, WFM_INPUT, RTA_INPUT, PERSONNEL_INPUT,
        LD_INPUT, CX_INPUT, CRM_INPUT
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = pathlib.Path(tmpdir) / "wf.db"
        audit_path = pathlib.Path(tmpdir) / "audit.db"
        log_path = pathlib.Path(tmpdir) / "logs.jsonl"

        engine = Engine(db_path=str(db_path))
        register_all(engine)

        from control_plane.vertical_slice import VerticalSliceController, VerticalSliceRequest

        ctrl = VerticalSliceController(engine, audit_db_path=str(audit_path), log_path=str(log_path))

        req = VerticalSliceRequest(
            tenant_id=TENANT_ID, client_id=CLIENT_ID,
            actor_suby=ACTOR_SUBY, actor_sami=ACTOR_SAMI,
            actor_compliance=ACTOR_COMPLIANCE, actor_phili=ACTOR_PHILI,
            actor_wili=ACTOR_WILI, actor_sales=ACTOR_SALES,
            approve_compliance=True, is_sample=True,
            wfm_input=WFM_INPUT, rta_input=RTA_INPUT,
            personnel_input=PERSONNEL_INPUT, ld_input=LD_INPUT,
            cx_input=CX_INPUT, crm_input=CRM_INPUT,
        )

        ev = ctrl.run(req)
        assert ev.final_state == "closed"
        assert len(ev.steps) == 9


def test_ollama_unavailable_behavior():
    """New agents handle Ollama unavailable gracefully."""
    for name in ["COMPLIANCE", "FRAUD", "MARKETING", "SALES", "ICT"]:
        agent = AgentRegistry.get_agent(name)
        # This will attempt to call Ollama and get an error, but should not crash
        result = agent.process_request("test query")
        assert isinstance(result, str)
        # Should contain error message or fallback
        assert len(result) > 0


def test_catalog_only_gms_no_execution_tools():
    """Catalog-only GMs don't claim unavailable execution tools."""
    catalog = load_role_catalog("organization/role-catalog.yaml")
    roles_by_id = catalog["roles_by_id"]

    for role_id in ["compliance_quality_gm", "fraud_gm", "marketing_gm", "sales_gm", "ict_gm"]:
        tools = roles_by_id[role_id]["allowed_tools"]
        # Should not have wfm_engine, rta_engine, cx_engine (execution tools)
        assert "wfm_engine" not in tools
        assert "rta_engine" not in tools
        assert "cx_engine" not in tools
        assert "personnel_engine" not in tools
        # Should have read-only or policy tools
        assert "ollama" in tools
        assert "cognitive_log" in tools


# ── KPI Vocabulary Tests ──

def test_kpi_vocabulary_complete():
    """All KPIs in vocabulary are used by at least one role."""
    catalog = load_role_catalog("organization/role-catalog.yaml")
    vocab = set(catalog["kpi_vocabulary"])
    used_kpis = set()
    for role in catalog["roles"]:
        used_kpis.update(role.get("kpis", []))

    # All vocab KPIs should be used
    for kpi in vocab:
        assert kpi in used_kpis, f"KPI {kpi!r} in vocabulary but not used by any role"

    # All used KPIs should be in vocabulary
    for kpi in used_kpis:
        assert kpi in vocab, f"KPI {kpi!r} used by role but not in vocabulary"


# ── Data Domain Tests ──

def test_new_gms_readable_data_domains():
    """New GMs have appropriate readable_data_domains."""
    catalog = load_role_catalog("organization/role-catalog.yaml")
    roles_by_id = catalog["roles_by_id"]

    # Compliance reads everything including regulated
    compliance_domains = roles_by_id["compliance_quality_gm"]["readable_data_domains"]
    assert "regulated" in compliance_domains
    assert "personnel" in compliance_domains
    assert "financial" in compliance_domains
    assert "client-confidential" in compliance_domains

    # Fraud reads financial and client-confidential
    fraud_domains = roles_by_id["fraud_gm"]["readable_data_domains"]
    assert "financial" in fraud_domains
    assert "client-confidential" in fraud_domains

    # Marketing reads public, internal, crm, sales
    marketing_domains = roles_by_id["marketing_gm"]["readable_data_domains"]
    assert "public" in marketing_domains
    assert "crm" in marketing_domains
    assert "sales" in marketing_domains

    # Sales reads financial, crm, b2b
    sales_domains = roles_by_id["sales_gm"]["readable_data_domains"]
    assert "financial" in sales_domains
    assert "crm" in sales_domains
    assert "b2b" in sales_domains

    # ICT reads platform, infrastructure, security, audit
    ict_domains = roles_by_id["ict_gm"]["readable_data_domains"]
    assert "platform" in ict_domains
    assert "security" in ict_domains
    assert "audit" in ict_domains


if __name__ == "__main__":
    pytest.main([__file__, "-v"])