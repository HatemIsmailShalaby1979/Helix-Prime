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


def _corr(
    tenant: str | None = "helix-prime", client: str | None = "Account Alpha"
) -> CorrelationContext:
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


def _valid_task_request(
    corr: CorrelationContext | None = None, requires_approval: bool = False
) -> TaskRequest:
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
    assert (
        EvidenceRef(evidence_id="ev1", type="log", uri="uri", timestamp=FIXED_TS).schema_version
        == "1.0"
    )
    # CorrelationContext
    assert c.schema_version == "1.0"
    assert (
        CorrelationContext(
            correlation_id="corr1",
            idempotency_key="idem1",
            tenant_id="t",
            client_id=None,
            created_at=FIXED_TS,
        ).schema_version
        == "1.0"
    )
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
        EvidenceRef(
            evidence_id="ev1", type="log", uri="uri", timestamp=FIXED_TS, schema_version="12"
        )
    with pytest.raises(ValueError, match="schema_version.*must be semver"):
        EvidenceRef(
            evidence_id="ev1", type="log", uri="uri", timestamp=FIXED_TS, schema_version="bad"
        )
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


# ══════════════════════════════════════════════════════════════════════════
# Phase 3 — Governance runtime: contract layer + fail-closed event store.
#
# Covers the three execution paths required by the enterprise organization model:
#   1. a successful valid request admitted inside every boundary
#   2. a boundary breach (engine outside the actor's owned_engines)
#   3. an over-budget financial trigger frozen for human validation
# The suite also proves the database traps violations instead of crashing.
# ══════════════════════════════════════════════════════════════════════════

import uuid as _uuid

from control_plane.governance import (
    MIN_AUTONOMY_CONFIDENCE,
    ORGANIZATION_CATALOG,
    AccessDeniedError,
    CorrelationContext as GovernanceCorrelationContext,
    GovernanceStateError,
    GovernedWorkflowManager,
    TaskRequest as GovernanceTaskRequest,
    detect_catalog_drift,
    evaluate_gate,
    get_role,
    resolve_actor_role,
)
from control_plane.store import Store as GovernanceStore
from control_plane.workflow import WorkflowState

GOV_TS = "2026-09-07T00:00:00Z"

# Financial approval limits from the canonical organization catalog (USD).
SPEC_FINANCIAL_LIMITS = {
    "sami": None,  # unlimited, human-escalated
    "ops_gm": 500.00,
    "compliance_quality_gm": 0.00,
    "fraud_revenue_gm": 0.00,
    "hr_personnel_gm": 1_000.00,
    "ld_gm": 200.00,
    "sales_gm": 2_500.00,
    "marketing_gm": 500.00,
    "ict_gm": 5_000.00,
}

SPEC_OWNED_ENGINES = {
    "ops_gm": {"wfm", "rta", "cx"},
    "compliance_quality_gm": set(),
    "fraud_revenue_gm": {"crm", "b2b"},
    "hr_personnel_gm": {"personnel", "wfm"},
    "ld_gm": {"wfm"},
    "sales_gm": {"crm", "b2b"},
    "marketing_gm": {"crm"},
    "ict_gm": {"control_plane"},
}


def _gov_corr(actor: str = "suby") -> GovernanceCorrelationContext:
    return GovernanceCorrelationContext(
        correlation_id=str(_uuid.uuid4()),
        idempotency_key=str(_uuid.uuid4()),
        tenant_id="helix-prime",
        client_id="Account Alpha",
        created_at=GOV_TS,
        actor_id=actor,
    )


def _gov_request(
    actor: str = "suby",
    role: str = "ops_gm",
    engine: str = "wfm",
    cost: float = 0.0,
    confidence: float = 0.95,
    classification: str = "internal",
    requires_approval: bool = False,
) -> GovernanceTaskRequest:
    return GovernanceTaskRequest(
        request_id="req_" + _uuid.uuid4().hex[:10],
        correlation=_gov_corr(actor),
        requesting_actor=actor,
        owning_role_id=role,
        capability="wfm_forecast",
        input_payload={"client": "Account Alpha", "estimated_financial_cost": cost},
        requires_approval=requires_approval,
        status="proposed",
        created_at=GOV_TS,
        tenant_id="helix-prime",
        client_id="Account Alpha",
        target_engine=engine,
        estimated_financial_cost=cost,
        confidence_score=confidence,
        requested_data_classification=classification,
    )


def _gov_manager(tmp_path) -> GovernedWorkflowManager:
    store = GovernanceStore(db_path=str(tmp_path / "governance.db"))
    return GovernedWorkflowManager(store=store)


# ── canonical catalog ─────────────────────────────────────────────────────


def test_organization_catalog_has_nine_seats():
    """8 Functional GMs + SAMI, and nothing else."""
    assert len(ORGANIZATION_CATALOG) == 9
    assert "sami" in ORGANIZATION_CATALOG
    assert len([r for r in ORGANIZATION_CATALOG if r.endswith("_gm")]) == 8


def test_organization_catalog_matches_spec_financial_limits():
    for role_id, limit in SPEC_FINANCIAL_LIMITS.items():
        spec = get_role(role_id)
        assert (
            spec.financial_approval_limit_usd == limit
        ), f"{role_id}: expected limit {limit}, got {spec.financial_approval_limit_usd}"


def test_organization_catalog_matches_spec_engine_ownership():
    for role_id, engines in SPEC_OWNED_ENGINES.items():
        assert set(get_role(role_id).owned_engines) == engines, f"{role_id}: owned_engines mismatch"


def test_sami_is_the_only_unlimited_seat():
    unlimited = [
        r for r, s in ORGANIZATION_CATALOG.items() if s.financial_approval_limit_usd is None
    ]
    assert unlimited == ["sami"]


def test_compliance_gm_is_oversight_only():
    assert get_role("compliance_quality_gm").oversight_only is True
    assert get_role("compliance_quality_gm").owned_engines == ()


def test_unknown_role_fails_closed():
    with pytest.raises(ValueError, match="unknown role_id"):
        get_role("chief_vibes_officer")


def test_actor_aliases_resolve_to_catalog_roles():
    assert resolve_actor_role("suby") == "ops_gm"
    assert resolve_actor_role("liza") == "sales_gm"
    assert resolve_actor_role("wili") == "ld_gm"
    assert resolve_actor_role("nono") == "fraud_revenue_gm"
    assert resolve_actor_role("sami") == "sami"


def test_catalog_drift_detector_reports_without_raising():
    """Drift is surfaced, not swallowed. Callers decide whether it is fatal."""
    drift = detect_catalog_drift()
    assert isinstance(drift, list)
    for entry in drift:
        assert {"role_id", "field", "runtime", "yaml", "detail"} <= set(entry)


# ── contract layer validation ─────────────────────────────────────────────


def test_correlation_context_requires_uuid4():
    with pytest.raises(ValueError, match="UUID4"):
        GovernanceCorrelationContext(
            correlation_id="corr_not_a_uuid",
            idempotency_key=str(_uuid.uuid4()),
            tenant_id="helix-prime",
            client_id="Account Alpha",
            created_at=GOV_TS,
        )


def test_correlation_context_accepts_uuid4_and_round_trips():
    ctx = _gov_corr("suby")
    restored = GovernanceCorrelationContext.from_dict(ctx.to_dict())
    assert restored.correlation_id == ctx.correlation_id
    assert restored.actor_id == "suby"


def test_task_request_rejects_confidence_out_of_bounds():
    with pytest.raises(ValueError, match="confidence must be 0.0-1.0"):
        _gov_request(confidence=1.4)


def test_task_request_rejects_negative_cost():
    with pytest.raises(ValueError, match="must be >= 0"):
        _gov_request(cost=-1.0)


def test_task_request_rejects_unknown_data_classification():
    with pytest.raises(ValueError, match="unknown classification"):
        _gov_request(classification="top_secret")


def test_governance_task_request_is_a_canonical_task_request():
    """The governance contract must stay a valid input to the existing engine."""
    from contracts.task import TaskRequest as CanonicalTaskRequest

    assert isinstance(_gov_request(), CanonicalTaskRequest)


# ── path 1: successful valid request ──────────────────────────────────────


def test_valid_request_is_admitted_and_executes(tmp_path):
    mgr = _gov_manager(tmp_path)
    record = mgr.submit(_gov_request(actor="suby", role="ops_gm", engine="wfm", cost=100.0))

    assert record.state == WorkflowState.EXECUTING
    assert record.reason_code == "within_bounds"
    assert record.actor_role_id == "ops_gm"
    assert record.financial_limit_usd == 500.00

    persisted = mgr.get_task(record.task_id)
    assert persisted is not None
    assert persisted.state == WorkflowState.EXECUTING


def test_valid_request_writes_a_hash_chained_audit_trail(tmp_path):
    mgr = _gov_manager(tmp_path)
    record = mgr.submit(_gov_request(cost=100.0))

    trail = mgr.audit_trail(task_id=record.task_id)
    assert len(trail) >= 3  # proposed -> validated -> executing
    assert [e["to_state"] for e in trail] == [
        WorkflowState.PROPOSED,
        WorkflowState.VALIDATED,
        WorkflowState.EXECUTING,
    ]
    assert mgr.verify_audit_chain() is True


# ── path 2: boundary breach (wrong engine ownership) ──────────────────────


def test_ownership_breach_raises_access_denied_at_contract_level():
    """sales_gm owns crm/b2b only — requesting wfm is an Access Denied."""
    with pytest.raises(AccessDeniedError, match="Access Denied"):
        _gov_request(actor="liza", role="sales_gm", engine="wfm", cost=10.0)


def test_ownership_breach_is_also_trapped_by_the_gate():
    decision = evaluate_gate("sales_gm", target_engine="wfm", estimated_financial_cost=10.0)
    assert decision.allowed is False
    assert decision.reason_code == "access_denied"
    assert decision.state == WorkflowState.DEAD_LETTER


def test_oversight_only_role_cannot_claim_any_engine():
    decision = evaluate_gate("compliance_quality_gm", target_engine="wfm")
    assert decision.allowed is False
    assert decision.reason_code == "access_denied"


def test_classification_breach_is_isolated_not_executed(tmp_path):
    """ops_gm may not touch regulated_high_risk data — trapped, not crashed."""
    mgr = _gov_manager(tmp_path)
    record = mgr.submit(_gov_request(engine="wfm", cost=10.0, classification="regulated_high_risk"))
    assert record.state == WorkflowState.DEAD_LETTER
    assert record.reason_code == "classification_not_permitted"
    assert record.error["code"] == "classification_not_permitted"
    assert mgr.audit_trail(task_id=record.task_id)[-1]["decision"] == "denied"


# ── path 3: over-budget financial trigger ─────────────────────────────────


@pytest.mark.parametrize(
    "role,actor,engine,cost,limit",
    [
        ("ops_gm", "suby", "wfm", 500.01, 500.00),
        ("ld_gm", "wili", "wfm", 200.01, 200.00),
        ("sales_gm", "liza", "crm", 2_500.01, 2_500.00),
        ("hr_personnel_gm", "phili", "personnel", 1_000.01, 1_000.00),
        ("ict_gm", "tomy", "control_plane", 5_000.01, 5_000.00),
        ("marketing_gm", "maya", "crm", 500.01, 500.00),
    ],
)
def test_over_budget_task_is_frozen_awaiting_approval(tmp_path, role, actor, engine, cost, limit):
    mgr = _gov_manager(tmp_path)
    record = mgr.submit(_gov_request(actor=actor, role=role, engine=engine, cost=cost))

    assert record.state == WorkflowState.AWAITING_APPROVAL
    assert record.reason_code == "financial_limit_exceeded"
    assert record.financial_limit_usd == limit
    assert record.estimated_financial_cost == cost
    assert "exceeds role" in record.reason


def test_cost_exactly_at_limit_is_autonomous():
    """Boundary is 'crosses the threshold', not 'reaches it'."""
    decision = evaluate_gate("ops_gm", estimated_financial_cost=500.00)
    assert decision.requires_human_approval is False
    assert decision.state == WorkflowState.EXECUTING


def test_zero_limit_roles_freeze_any_spend():
    for role in ("compliance_quality_gm", "fraud_revenue_gm"):
        decision = evaluate_gate(role, estimated_financial_cost=0.01)
        assert decision.requires_human_approval is True
        assert decision.reason_code == "financial_limit_exceeded"


def test_sami_unlimited_still_autonomous_at_scale():
    decision = evaluate_gate("sami", estimated_financial_cost=1_000_000.00)
    assert decision.requires_human_approval is False


def test_low_confidence_freezes_for_human_review(tmp_path):
    mgr = _gov_manager(tmp_path)
    record = mgr.submit(_gov_request(cost=10.0, confidence=MIN_AUTONOMY_CONFIDENCE - 0.01))
    assert record.state == WorkflowState.AWAITING_APPROVAL
    assert record.reason_code == "low_confidence"


def test_frozen_task_cannot_skip_the_approval_queue(tmp_path):
    mgr = _gov_manager(tmp_path)
    record = mgr.submit(_gov_request(cost=900.0))
    assert record.state == WorkflowState.AWAITING_APPROVAL

    # A direct attempt to jump to executing must be rejected by the state machine.
    with pytest.raises(GovernanceStateError, match="invalid transition"):
        mgr._commit_state(record, WorkflowState.EXECUTING, "sami")


# ── human validation token ────────────────────────────────────────────────


def test_human_approval_releases_frozen_task(tmp_path):
    mgr = _gov_manager(tmp_path)
    record = mgr.submit(_gov_request(cost=900.0))
    assert record.state == WorkflowState.AWAITING_APPROVAL

    approved = mgr.approve(record.task_id, "sami", note="exec sign-off")
    assert approved.state == WorkflowState.EXECUTING

    done = mgr.complete(record.task_id, WorkflowState.SUCCEEDED, output_payload={"staffed": 12})
    assert done.state == WorkflowState.SUCCEEDED


def test_self_approval_is_refused(tmp_path):
    mgr = _gov_manager(tmp_path)
    record = mgr.submit(_gov_request(actor="suby", cost=900.0))
    with pytest.raises(GovernanceStateError, match="segregation of duties"):
        mgr.approve(record.task_id, "suby")


def test_approver_own_limit_must_cover_the_task(tmp_path):
    mgr = _gov_manager(tmp_path)
    record = mgr.submit(_gov_request(actor="suby", role="ops_gm", cost=900.0))
    # ld_gm limit is 200.00 — cannot release a 900.00 task.
    with pytest.raises(GovernanceStateError, match="escalate to SAMI"):
        mgr.approve(record.task_id, "wili")


def test_reject_cancels_frozen_task(tmp_path):
    mgr = _gov_manager(tmp_path)
    record = mgr.submit(_gov_request(cost=900.0))
    cancelled = mgr.reject(record.task_id, "sami", note="not this quarter")
    assert cancelled.state == WorkflowState.CANCELLED


def test_approving_a_non_frozen_task_is_refused(tmp_path):
    mgr = _gov_manager(tmp_path)
    record = mgr.submit(_gov_request(cost=10.0))  # executes immediately
    with pytest.raises(GovernanceStateError, match="not awaiting_approval"):
        mgr.approve(record.task_id, "sami")


# ── durability: the database traps violations safely ──────────────────────


def test_audit_ledger_is_append_only(tmp_path):
    mgr = _gov_manager(tmp_path)
    record = mgr.submit(_gov_request(cost=10.0))

    with pytest.raises(Exception, match="append-only"):
        mgr.store.conn.execute("DELETE FROM audit_events WHERE task_id = ?", (record.task_id,))
    with pytest.raises(Exception, match="append-only"):
        mgr.store.conn.execute("UPDATE audit_events SET decision = 'allowed'")


def test_audit_chain_detects_tampering(tmp_path):
    mgr = _gov_manager(tmp_path)
    mgr.submit(_gov_request(cost=10.0))
    assert mgr.verify_audit_chain() is True

    # Tamper outside the API (drop the append-only trigger first).
    first = mgr.audit_trail(task_id=None)[0]
    mgr.store.conn.execute("DROP TRIGGER trg_audit_events_no_update")
    mgr.store.conn.execute(
        "UPDATE audit_events SET decision = 'denied' WHERE event_id = ?", (first["event_id"],)
    )
    mgr.store.conn.commit()
    assert mgr.verify_audit_chain() is False


def test_ledger_rejects_forked_append(tmp_path):
    mgr = _gov_manager(tmp_path)
    mgr.submit(_gov_request(cost=10.0))
    head = mgr.store.get_last_audit_hash()
    assert head != ""

    from control_plane.governance import AuditEventRecord

    forked = AuditEventRecord(
        event_id=str(_uuid.uuid4()),
        occurred_at=GOV_TS,
        correlation_id="corr_fork",
        actor_id="attacker",
        actor_role_id="ops_gm",
        event_type="task_executing",
        decision="allowed",
        reason_code="forged",
        reason="forged entry",
        prev_hash="deadbeef",
    )
    forked.record_hash = forked.compute_hash()
    with pytest.raises(ValueError, match="ledger fork rejected"):
        mgr.store.append_audit_event(forked.to_dict())


def test_unsigned_audit_event_is_rejected(tmp_path):
    mgr = _gov_manager(tmp_path)
    with pytest.raises(ValueError, match="record_hash is required"):
        mgr.store.append_audit_event({"event_id": str(_uuid.uuid4()), "prev_hash": ""})


def test_duplicate_task_id_fails_deterministically(tmp_path):
    mgr = _gov_manager(tmp_path)
    record = mgr.submit(_gov_request(cost=10.0))
    with pytest.raises(Exception):
        mgr.store.insert_workflow_task(record.to_dict())


def test_manager_survives_a_stream_of_violations(tmp_path):
    """The engine must not crash while the database traps every violation."""
    mgr = _gov_manager(tmp_path)

    mgr.submit(_gov_request(cost=10.0))  # ok
    mgr.submit(_gov_request(cost=9_999.0))  # frozen
    mgr.submit(_gov_request(cost=10.0, classification="regulated_high_risk"))  # isolated
    mgr.submit(_gov_request(cost=10.0, confidence=0.1))  # frozen

    states = [t.state for t in mgr.list_tasks()]
    assert WorkflowState.EXECUTING in states
    assert states.count(WorkflowState.AWAITING_APPROVAL) == 2
    assert WorkflowState.DEAD_LETTER in states
    assert mgr.verify_audit_chain() is True


# ── engine integration ────────────────────────────────────────────────────


def test_engine_submit_holds_over_budget_request(tmp_path):
    """The runtime orchestrator freezes an over-budget task before execution."""
    from control_plane.engine import Engine
    from control_plane.store import Store

    store = Store(db_path=str(tmp_path / "engine_gate.db"))
    engine = Engine(store=store)
    engine.register_handler("wfm_forecast", lambda wf: {"staffed": 1})

    req = _gov_request(actor="suby", role="ops_gm", engine="wfm", cost=600.0)
    workflow = engine.submit(req)

    assert workflow.state == WorkflowState.AWAITING_APPROVAL
    assert workflow.requires_approval is True


def test_engine_submit_still_executes_in_budget_request(tmp_path):
    from control_plane.engine import Engine
    from control_plane.store import Store

    store = Store(db_path=str(tmp_path / "engine_gate2.db"))
    engine = Engine(store=store)
    engine.register_handler("wfm_forecast", lambda wf: {"staffed": 1})

    req = _gov_request(actor="suby", role="ops_gm", engine="wfm", cost=100.0)
    workflow = engine.submit(req)

    assert workflow.state == WorkflowState.EXECUTING
