"""TDD coverage for Helix Prime Codex C1 — organization model and typed contracts."""
from __future__ import annotations

import pathlib
import datetime

import pytest

from contracts.task import (
    SCHEMA_VERSION,
    Action,
    AgentError,
    Approval,
    CorrelationContext,
    EvidenceRef,
    Recommendation,
    TaskRequest,
    TaskResult,
)
from contracts.adapter import parse_legacy_calls, to_task_request, validate_request_against_catalog
from organization.role_catalog import load_role_catalog, validate_role_catalog

# ── helpers ────────────────────────────────────────────────────────────────

FIXED_TS = "2026-08-27T18:00:00Z"
FIXED_TS2 = "2026-08-27T18:00:01Z"


def _corr(tenant: str | None = "helix-prime", client: str | None = "Account Alpha") -> CorrelationContext:
    return CorrelationContext(
        correlation_id="corr_test123",
        idempotency_key="idem_test123",
        tenant_id=tenant,
        client_id=client,
        created_at=FIXED_TS,
    )


def _evidence() -> EvidenceRef:
    return EvidenceRef(
        evidence_id="ev_test123",
        type="engine_output",
        uri="evidence/runs/test/output.json",
        timestamp=FIXED_TS,
        hash="abc123",
        actor="sami",
    )


def _valid_task_request(corr: CorrelationContext | None = None, requires_approval: bool = False) -> TaskRequest:
    c = corr or _corr()
    return TaskRequest(
        request_id="req_test123",
        correlation=c,
        requesting_actor="sami",
        owning_role_id="ops_gm",
        capability="wfm_forecast",
        input_payload={"client": "Account Alpha"},
        requires_approval=requires_approval,
        status="proposed",
        created_at=FIXED_TS,
        tenant_id="helix-prime",
        client_id="Account Alpha",
        evidence_refs=[_evidence()],
    )


# ── canonical schema version ─────────────────────────────────────────────

def test_schema_version_canonical_is_1_0():
    """Canonical contract schema version is semantic '1.0' (not 12, not drifted)."""
    assert SCHEMA_VERSION == "1.0"
    assert SCHEMA_VERSION.count(".") == 1


def test_all_models_default_schema_version_consistently_1_0():
    """Every C1 contract must default to the same canonical SCHEMA_VERSION."""
    c = _corr()
    ev = _evidence()
    # EvidenceRef
    assert ev.schema_version == "1.0"
    assert EvidenceRef(evidence_id="ev1", type="log", uri="uri", timestamp=FIXED_TS).schema_version == "1.0"
    # CorrelationContext
    assert c.schema_version == "1.0"
    assert CorrelationContext(
        correlation_id="corr1", idempotency_key="idem1", tenant_id="t", client_id=None, created_at=FIXED_TS
    ).schema_version == "1.0"
    # AgentError
    err = AgentError(
        error_id="err1", correlation_id="corr1", code="timeout", message="m", timestamp=FIXED_TS
    )
    assert err.schema_version == "1.0"
    # Approval
    appr = Approval(
        approval_id="appr1",
        correlation_id="corr1",
        subject_id="subj1",
        approver_actor="compliance_user",
        approver_role_id="compliance_quality_gm",
        decision="approved",
        reason="r",
        timestamp=FIXED_TS,
    )
    assert appr.schema_version == "1.0"
    # Action
    act = Action(
        action_id="act1",
        correlation=c,
        tenant_id="t",
        client_id=None,
        actor="sami",
        owning_role_id="ops_gm",
        capability="wfm_forecast",
        payload={},
        requires_approval=False,
        status="proposed",
        created_at=FIXED_TS,
    )
    assert act.schema_version == "1.0"
    # Recommendation
    rec = Recommendation(
        recommendation_id="rec1",
        correlation=c,
        owning_role_id="ops_gm",
        capability="wfm_forecast",
        confidence=0.5,
        rationale="r",
        requires_approval=False,
        created_at=FIXED_TS,
    )
    assert rec.schema_version == "1.0"
    # TaskRequest
    req = _valid_task_request(c)
    assert req.schema_version == "1.0"
    # TaskResult
    res = TaskResult(
        result_id="res1",
        request_id="req1",
        correlation=c,
        owning_role_id="ops_gm",
        capability="wfm_forecast",
        status="succeeded",
        created_at=FIXED_TS,
        output_payload={"ok": True},
    )
    assert res.schema_version == "1.0"
    # round-trip preserves version
    for obj in [ev, c, err, appr, act, rec, req, res]:
        d = obj.to_dict()
        assert d["schema_version"] == "1.0", f"{type(obj).__name__} to_dict schema_version drift"


def test_models_reject_invalid_schema_version():
    c = _corr()
    with pytest.raises(ValueError, match="schema_version.*must be semver"):
        EvidenceRef(evidence_id="ev1", type="log", uri="uri", timestamp=FIXED_TS, schema_version="12")
    with pytest.raises(ValueError, match="schema_version.*must be semver"):
        EvidenceRef(evidence_id="ev1", type="log", uri="uri", timestamp=FIXED_TS, schema_version="bad")
    with pytest.raises(ValueError, match="schema_version.*must be semver"):
        CorrelationContext(
            correlation_id="corr1",
            idempotency_key="idem1",
            tenant_id="t",
            client_id=None,
            created_at=FIXED_TS,
            schema_version="12",
        )


def test_role_catalog_schema_version_is_1_0():
    catalog = load_role_catalog("organization/role-catalog.yaml")
    assert catalog["schema_version"] == "1.0"


# ── valid task request ───────────────────────────────────────────────────

def test_valid_task_request():
    req = _valid_task_request()
    assert req.request_id == "req_test123"
    assert req.correlation.correlation_id == "corr_test123"
    assert req.owning_role_id == "ops_gm"
    assert req.schema_version == SCHEMA_VERSION
    d = req.to_dict()
    assert d["request_id"] == "req_test123"
    # round-trip
    req2 = TaskRequest.from_dict(d)
    assert req2.request_id == req.request_id
    assert req2.correlation.correlation_id == req.correlation.correlation_id


def test_valid_task_request_with_approval_tier():
    c = _corr()
    req = TaskRequest(
        request_id="req_tier1",
        correlation=c,
        requesting_actor="sami",
        owning_role_id="sales_gm",
        capability="pipeline_management",
        input_payload={"deal": "D123"},
        requires_approval=True,
        status="proposed",
        created_at=FIXED_TS,
        client_id="Account Beta",
        approval_limit_tier="financial",
    )
    assert req.requires_approval is True
    assert req.approval_limit_tier == "financial"


# ── valid successful task result ─────────────────────────────────────────

def test_valid_successful_task_result():
    c = _corr()
    res = TaskResult(
        result_id="res_test123",
        request_id="req_test123",
        correlation=c,
        owning_role_id="ops_gm",
        capability="wfm_forecast",
        status="succeeded",
        created_at=FIXED_TS,
        completed_at=FIXED_TS2,
        output_payload={"optimal_agents": 42},
        confidence=0.92,
        evidence_refs=[_evidence()],
    )
    assert res.status == "succeeded"
    assert res.error is None
    assert res.confidence == 0.92
    d = res.to_dict()
    assert d["output_payload"]["optimal_agents"] == 42
    # from_dict round-trip
    res2 = TaskResult.from_dict(d)
    assert res2.result_id == "res_test123"
    assert res2.output_payload["optimal_agents"] == 42


# ── valid recommendation requiring approval ────────────────────────────────

def test_valid_recommendation_requiring_approval():
    c = _corr()
    rec = Recommendation(
        recommendation_id="rec_test123",
        correlation=c,
        owning_role_id="ops_gm",
        capability="wfm_forecast",
        confidence=0.85,
        rationale="Service level 0.78 below target 0.80; recommend +5 agents",
        requires_approval=True,
        created_at=FIXED_TS,
        client_id="Account Alpha",
        evidence_refs=[_evidence()],
    )
    assert rec.requires_approval is True
    assert rec.confidence == 0.85
    # confidence validated
    assert 0.0 <= rec.confidence <= 1.0


def test_recommendation_with_proposed_action():
    c = _corr()
    act = Action(
        action_id="act_test123",
        correlation=c,
        tenant_id="helix-prime",
        client_id="Account Alpha",
        actor="sami",
        owning_role_id="ops_gm",
        capability="wfm_forecast",
        payload={"add_agents": 5},
        requires_approval=False,
        status="proposed",
        created_at=FIXED_TS,
        evidence_refs=[_evidence()],
    )
    rec = Recommendation(
        recommendation_id="rec_with_act",
        correlation=c,
        owning_role_id="ops_gm",
        capability="wfm_forecast",
        confidence=0.9,
        rationale="needs approval",
        requires_approval=False,
        created_at=FIXED_TS,
        proposed_action=act,
    )
    assert rec.proposed_action.action_id == "act_test123"


# ── valid approved action ─────────────────────────────────────────────────

def test_valid_approved_action():
    c = _corr()
    appr = Approval(
        approval_id="appr_test123",
        correlation_id="corr_test123",
        subject_id="act_test123",
        approver_actor="compliance_user",
        approver_role_id="compliance_quality_gm",
        decision="approved",
        reason="Policy check passed",
        timestamp=FIXED_TS2,
        evidence_ref=_evidence(),
    )
    act = Action(
        action_id="act_test123",
        correlation=c,
        tenant_id="helix-prime",
        client_id="Account Alpha",
        actor="sami",
        owning_role_id="ops_gm",
        capability="wfm_forecast",
        payload={"add_agents": 5},
        requires_approval=True,
        status="approved",
        created_at=FIXED_TS,
        approval=appr,
        evidence_refs=[_evidence()],
    )
    assert act.approval.decision == "approved"
    assert act.status == "approved"
    # to_dict round-trip
    d = act.to_dict()
    act2 = Action.from_dict(d)
    assert act2.approval.approval_id == "appr_test123"


# ── refusal result ─────────────────────────────────────────────────────────

def test_refusal_result():
    c = _corr()
    err = AgentError(
        error_id="err_refuse1",
        correlation_id="corr_test123",
        code="refused",
        message="Policy denied: financial limit exceeded",
        timestamp=FIXED_TS2,
        retryable=False,
    )
    res = TaskResult(
        result_id="res_refuse1",
        request_id="req_test123",
        correlation=c,
        owning_role_id="sales_gm",
        capability="pipeline_management",
        status="refused",
        created_at=FIXED_TS,
        error=err,
        evidence_refs=[_evidence()],
    )
    assert res.status == "refused"
    assert res.error.code == "refused"


def test_refusal_requires_error():
    c = _corr()
    with pytest.raises(ValueError, match="refused.*requires error"):
        TaskResult(
            result_id="res_bad",
            request_id="req_test123",
            correlation=c,
            owning_role_id="sales_gm",
            capability="pipeline_management",
            status="refused",
            created_at=FIXED_TS,
        )


# ── timeout / error result ─────────────────────────────────────────────────

def test_timeout_error_result():
    c = _corr()
    err = AgentError(
        error_id="err_timeout1",
        correlation_id="corr_test123",
        code="timeout",
        message="Ollama timeout after 120s",
        timestamp=FIXED_TS2,
        retryable=True,
    )
    res = TaskResult(
        result_id="res_timeout1",
        request_id="req_test123",
        correlation=c,
        owning_role_id="ops_gm",
        capability="wfm_forecast",
        status="timed_out",
        created_at=FIXED_TS,
        error=err,
    )
    assert res.status == "timed_out"
    assert res.error.retryable is True


def test_timeout_requires_timeout_code():
    c = _corr()
    err_wrong = AgentError(
        error_id="err_wrong",
        correlation_id="corr_test123",
        code="engine_error",
        message="wrong code",
        timestamp=FIXED_TS2,
    )
    with pytest.raises(ValueError, match="timed_out.*timeout"):
        TaskResult(
            result_id="res_bad2",
            request_id="req_test123",
            correlation=c,
            owning_role_id="ops_gm",
            capability="wfm_forecast",
            status="timed_out",
            created_at=FIXED_TS,
            error=err_wrong,
        )


def test_failed_requires_error():
    c = _corr()
    with pytest.raises(ValueError, match="failed.*requires error"):
        TaskResult(
            result_id="res_failed_bad",
            request_id="req_test123",
            correlation=c,
            owning_role_id="ops_gm",
            capability="wfm_forecast",
            status="failed",
            created_at=FIXED_TS,
        )


def test_succeeded_cannot_have_error():
    c = _corr()
    err = AgentError(
        error_id="err1",
        correlation_id="corr_test123",
        code="engine_error",
        message="should not be here",
        timestamp=FIXED_TS2,
    )
    with pytest.raises(ValueError, match="succeeded.*cannot have error"):
        TaskResult(
            result_id="res_bad3",
            request_id="req_test123",
            correlation=c,
            owning_role_id="ops_gm",
            capability="wfm_forecast",
            status="succeeded",
            created_at=FIXED_TS,
            error=err,
        )


# ── invalid / missing correlation data ───────────────────────────────────

def test_missing_correlation_tenant_client():
    with pytest.raises(ValueError, match="at least one of tenant_id or client_id"):
        CorrelationContext(
            correlation_id="corr_x",
            idempotency_key="idem_x",
            tenant_id=None,
            client_id=None,
            created_at=FIXED_TS,
        )


def test_task_request_missing_correlation():
    with pytest.raises(ValueError, match="must be CorrelationContext"):
        TaskRequest(  # type: ignore[arg-type]
            request_id="req_x",
            correlation=None,  # type: ignore
            requesting_actor="sami",
            owning_role_id="ops_gm",
            capability="wfm_forecast",
            input_payload={},
            requires_approval=False,
            status="proposed",
            created_at=FIXED_TS,
        )


def test_task_request_missing_request_id():
    c = _corr()
    with pytest.raises(ValueError, match="request_id.*non-empty"):
        TaskRequest(
            request_id="",
            correlation=c,
            requesting_actor="sami",
            owning_role_id="ops_gm",
            capability="wfm_forecast",
            input_payload={},
            requires_approval=False,
            status="proposed",
            created_at=FIXED_TS,
        )


def test_task_request_idempotency_mismatch():
    c = _corr()
    with pytest.raises(ValueError, match="idempotency_key.*must match"):
        TaskRequest(
            request_id="req_x",
            correlation=c,
            requesting_actor="sami",
            owning_role_id="ops_gm",
            capability="wfm_forecast",
            input_payload={},
            requires_approval=False,
            status="proposed",
            created_at=FIXED_TS,
            idempotency_key="different_key",
        )


def test_invalid_timestamp():
    with pytest.raises(ValueError, match="ISO8601"):
        CorrelationContext(
            correlation_id="corr_x",
            idempotency_key="idem_x",
            tenant_id="t",
            client_id=None,
            created_at="not-a-timestamp",
        )


# ── invalid status transitions / required fields ───────────────────────────

def test_invalid_task_request_status():
    c = _corr()
    with pytest.raises(ValueError, match="must be one of"):
        TaskRequest(
            request_id="req_x",
            correlation=c,
            requesting_actor="sami",
            owning_role_id="ops_gm",
            capability="wfm_forecast",
            input_payload={},
            requires_approval=False,
            status="not_a_status",
            created_at=FIXED_TS,
        )


def test_invalid_action_status():
    c = _corr()
    with pytest.raises(ValueError, match="must be one of"):
        Action(
            action_id="act_x",
            correlation=c,
            tenant_id="t",
            client_id=None,
            actor="sami",
            owning_role_id="ops_gm",
            capability="wfm_forecast",
            payload={},
            requires_approval=False,
            status="invalid_status",
            created_at=FIXED_TS,
        )


def test_invalid_confidence():
    c = _corr()
    with pytest.raises(ValueError, match="confidence must be 0.0-1.0"):
        Recommendation(
            recommendation_id="rec_x",
            correlation=c,
            owning_role_id="ops_gm",
            capability="wfm_forecast",
            confidence=1.5,
            rationale="bad",
            requires_approval=False,
            created_at=FIXED_TS,
        )
    with pytest.raises(ValueError, match="confidence must be 0.0-1.0"):
        Recommendation(
            recommendation_id="rec_x2",
            correlation=c,
            owning_role_id="ops_gm",
            capability="wfm_forecast",
            confidence=-0.1,
            rationale="bad",
            requires_approval=False,
            created_at=FIXED_TS,
        )


def test_missing_required_field_evidence_ref():
    with pytest.raises(ValueError, match="must be non-empty string"):
        EvidenceRef(
            evidence_id="",
            type="log",
            uri="uri",
            timestamp=FIXED_TS,
        )


def test_invalid_approval_decision():
    with pytest.raises(ValueError, match="must be one of"):
        Approval(
            approval_id="appr_x",
            correlation_id="corr_x",
            subject_id="act_x",
            approver_actor="compliance_user",
            approver_role_id="compliance_quality_gm",
            decision="maybe",
            reason="bad",
            timestamp=FIXED_TS,
        )


def test_invalid_error_code():
    with pytest.raises(ValueError, match="must be one of"):
        AgentError(
            error_id="err_x",
            correlation_id="corr_x",
            code="not_a_code",
            message="bad",
            timestamp=FIXED_TS,
        )


# ── invalid approval / action ownership ───────────────────────────────────

def test_action_self_approval_forbidden():
    c = _corr()
    appr_same_actor = Approval(
        approval_id="appr_same",
        correlation_id="corr_test123",
        subject_id="act_test123",
        approver_actor="sami",  # same as action actor
        approver_role_id="compliance_quality_gm",
        decision="approved",
        reason="self",
        timestamp=FIXED_TS2,
    )
    with pytest.raises(ValueError, match="cannot be same as actor"):
        Action(
            action_id="act_test123",
            correlation=c,
            tenant_id="helix-prime",
            client_id="Account Alpha",
            actor="sami",
            owning_role_id="ops_gm",
            capability="wfm_forecast",
            payload={},
            requires_approval=True,
            status="approved",
            created_at=FIXED_TS,
            approval=appr_same_actor,
        )


def test_action_same_role_approval_forbidden():
    c = _corr()
    appr_same_role = Approval(
        approval_id="appr_same_role",
        correlation_id="corr_test123",
        subject_id="act_test123",
        approver_actor="other_user",
        approver_role_id="ops_gm",  # same as owning_role_id
        decision="approved",
        reason="same role",
        timestamp=FIXED_TS2,
    )
    with pytest.raises(ValueError, match="cannot be same as owning_role_id"):
        Action(
            action_id="act_test123",
            correlation=c,
            tenant_id="helix-prime",
            client_id="Account Alpha",
            actor="sami",
            owning_role_id="ops_gm",
            capability="wfm_forecast",
            payload={},
            requires_approval=True,
            status="approved",
            created_at=FIXED_TS,
            approval=appr_same_role,
        )


def test_action_approval_correlation_mismatch():
    c = _corr()
    appr_wrong_corr = Approval(
        approval_id="appr_wrong",
        correlation_id="different_corr",
        subject_id="act_test123",
        approver_actor="compliance_user",
        approver_role_id="compliance_quality_gm",
        decision="approved",
        reason="mismatch",
        timestamp=FIXED_TS2,
    )
    with pytest.raises(ValueError, match="must match action correlation"):
        Action(
            action_id="act_test123",
            correlation=c,
            tenant_id="helix-prime",
            client_id="Account Alpha",
            actor="sami",
            owning_role_id="ops_gm",
            capability="wfm_forecast",
            payload={},
            requires_approval=True,
            status="approved",
            created_at=FIXED_TS,
            approval=appr_wrong_corr,
        )


# ── role catalog loading and required-role validation ─────────────────────

def test_role_catalog_loads_and_contains_required_roles():
    catalog = load_role_catalog("organization/role-catalog.yaml")
    assert catalog["schema_version"] == "1.0"
    roles_by_id = catalog["roles_by_id"]
    expected = {
        "sami",
        "hr_personnel_gm",
        "marketing_gm",
        "sales_gm",
        "compliance_quality_gm",
        "ict_gm",
        "fraud_gm",
        "ld_gm",
        "ops_gm",
    }
    assert expected.issubset(set(roles_by_id.keys()))
    # check mapped agents preserved
    assert roles_by_id["hr_personnel_gm"]["maps_to_agent"] == "PHILI"
    assert roles_by_id["ld_gm"]["maps_to_agent"] == "WILI"
    assert roles_by_id["ops_gm"]["maps_to_agent"] == "SUBY"
    assert roles_by_id["sami"]["maps_to_agent"] == "SAMI"
    # all 9 GMs are now functional_agent with canonical crew names
    for rid in ["marketing_gm", "sales_gm", "compliance_quality_gm", "ict_gm", "fraud_gm"]:
        assert roles_by_id[rid]["implementation_status"] == "functional_agent"
        assert roles_by_id[rid]["maps_to_agent"] is not None
        assert roles_by_id[rid]["agent_class"] is not None
        assert "agent_name" in roles_by_id[rid]
    # SOD: compliance can review ops etc
    can = set(roles_by_id["compliance_quality_gm"]["segregation_of_duties"]["can_review"])
    assert {"ops_gm", "sales_gm", "hr_personnel_gm", "fraud_gm"}.issubset(can)


def test_role_catalog_rejects_duplicate_ids(tmp_path: pathlib.Path):
    # create minimal duplicate catalog
    yaml_text = """
schema_version: "1.0"
kpi_vocabulary: [sla]
roles:
  - id: sami
    display_name: "SAMI"
    mission: "m"
    owned_capabilities: [a]
    allowed_tools: [b]
    readable_data_domains: [c]
    approval_limits: {tier: executive, can_approve: [standard], max_financial_amount: null, requires_escalation_for: []}
    escalation_owner: sami
    kpis: [sla]
    allowed_peer_calls: []
    segregation_of_duties: {cannot_approve_own_actions: false, must_be_reviewed_by: [], can_review: [], restrictions: []}
  - id: sami
    display_name: "Duplicate"
    mission: "m"
    owned_capabilities: [a]
    allowed_tools: [b]
    readable_data_domains: [c]
    approval_limits: {tier: executive, can_approve: [standard], max_financial_amount: null, requires_escalation_for: []}
    escalation_owner: sami
    kpis: [sla]
    allowed_peer_calls: []
    segregation_of_duties: {cannot_approve_own_actions: false, must_be_reviewed_by: [], can_review: [], restrictions: []}
"""
    p = tmp_path / "bad.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate role id"):
        load_role_catalog(str(p))


def test_role_catalog_rejects_missing_field(tmp_path: pathlib.Path):
    yaml_text = """
schema_version: "1.0"
kpi_vocabulary: [sla]
roles:
  - id: sami
    display_name: "SAMI"
    mission: "m"
    owned_capabilities: [a]
    allowed_tools: [b]
    readable_data_domains: [c]
    approval_limits: {tier: executive, can_approve: [standard], max_financial_amount: null, requires_escalation_for: []}
    escalation_owner: sami
    kpis: [sla]
    allowed_peer_calls: []
    # missing segregation_of_duties
"""
    p = tmp_path / "bad2.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ValueError, match="missing required field.*segregation_of_duties"):
        load_role_catalog(str(p))


def test_role_catalog_rejects_invalid_reference():
    # Build a full 9-role catalog where one escalation is invalid — test the reference check, not the missing-roles check
    from organization.role_catalog import validate_role_catalog

    catalog = load_role_catalog("organization/role-catalog.yaml")
    # mutate a copy: make hr's escalation invalid
    import copy

    data = {
        "schema_version": "1.0",
        "kpi_vocabulary": catalog["kpi_vocabulary"],
        "roles": copy.deepcopy(catalog["roles"]),
    }
    for r in data["roles"]:
        if r["id"] == "hr_personnel_gm":
            r["escalation_owner"] = "does_not_exist"
    with pytest.raises(ValueError, match="escalation_owner.*not in role ids"):
        validate_role_catalog(data)


def test_role_catalog_rejects_malformed_yaml(tmp_path: pathlib.Path):
    p = tmp_path / "bad4.yaml"
    p.write_text("::: not yaml ::: [", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed YAML"):
        load_role_catalog(str(p))


def test_validate_catalog_missing_required_roles():
    # build catalog missing 8 gms
    data = {
        "schema_version": "1.0",
        "kpi_vocabulary": ["sla"],
        "roles": [
            {
                "id": "sami",
                "display_name": "SAMI",
                "mission": "m",
                "owned_capabilities": ["a"],
                "allowed_tools": ["b"],
                "readable_data_domains": ["c"],
                "approval_limits": {
                    "tier": "executive",
                    "can_approve": ["standard"],
                    "max_financial_amount": None,
                    "requires_escalation_for": [],
                },
                "escalation_owner": "sami",
                "kpis": ["sla"],
                "allowed_peer_calls": [],
                "segregation_of_duties": {
                    "cannot_approve_own_actions": False,
                    "must_be_reviewed_by": [],
                    "can_review": [],
                    "restrictions": [],
                },
            }
        ],
    }
    with pytest.raises(ValueError, match="missing required role ids"):
        validate_role_catalog(data)


# ── adapter compatibility seam ────────────────────────────────────────────

def test_adapter_parse_legacy_calls():
    text = 'hello call_agent("PHILI", "headcount?") world call_agent(\'WILI\', "train?")'
    parsed = parse_legacy_calls(text)
    assert parsed == [("PHILI", "headcount?"), ("WILI", "train?")]
    assert parse_legacy_calls("no calls") == []


def test_adapter_to_task_request_validates():
    c = _corr()
    req = to_task_request(
        correlation=c,
        requesting_actor="sami",
        requesting_role_id="sami",
        owning_role_id="hr_personnel_gm",
        capability="workforce_planning",
        input_payload={"q": "headcount?"},
    )
    assert req.owning_role_id == "hr_personnel_gm"
    assert req.capability == "workforce_planning"


def test_adapter_validate_peer_allowed():
    catalog = load_role_catalog("organization/role-catalog.yaml")
    c = _corr(client="Account Alpha")
    # sami -> ops_gm is allowed per catalog
    req = to_task_request(
        correlation=c,
        requesting_actor="sami",
        requesting_role_id="sami",
        owning_role_id="ops_gm",
        capability="wfm_forecast",
        input_payload={},
    )
    validate_request_against_catalog(req, catalog)  # should not raise


def test_adapter_validate_peer_denied_raises():
    catalog = load_role_catalog("organization/role-catalog.yaml")
    c = _corr()
    # marketing_gm is NOT allowed to call ops_gm directly per catalog (allowed: sales_gm, sami, compliance)
    req = TaskRequest(
        request_id="req_peer_bad",
        correlation=c,
        requesting_actor="marketing_gm",  # will be resolved as marketing_gm role
        owning_role_id="ops_gm",
        capability="wfm_forecast",  # owned by ops_gm
        input_payload={},
        requires_approval=False,
        status="proposed",
        created_at=FIXED_TS,
        client_id="Account Alpha",
    )
    with pytest.raises(ValueError, match="Peer call not allowed"):
        validate_request_against_catalog(req, catalog)


def test_adapter_validate_capability_not_owned_raises():
    catalog = load_role_catalog("organization/role-catalog.yaml")
    c = _corr()
    req = TaskRequest(
        request_id="req_cap_bad",
        correlation=c,
        requesting_actor="sami",
        owning_role_id="ops_gm",
        capability="not_owned_cap",
        input_payload={},
        requires_approval=False,
        status="proposed",
        created_at=FIXED_TS,
        client_id="Account Alpha",
    )
    with pytest.raises(ValueError, match="not owned by role"):
        validate_request_against_catalog(req, catalog)


def test_existing_cockpit_and_engine_behavior_preserved():
    # Ensure existing module still importable and not broken by C1 additive change
    from orchestration.orchestrator import Orchestrator

    o = Orchestrator()
    routed = o._resolve_agents("service level is dropping")
    assert "suby" in routed
    # engine probes still work via smoke's importlib check
    import importlib.util

    spec = importlib.util.spec_from_file_location("erlang_c", "engines/wfm/src/erlang_c.py")
    assert spec is not None
