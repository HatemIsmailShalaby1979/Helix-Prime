"""
Tests for SOD integrity in control_plane/engine.py.

Verifies that:
- Unknown approver roles are denied (not silently allowed)
- The engine no longer hardcodes "sami" / "compliance_quality_gm" as super-roles
- Super-role authority comes from the catalog's universal_approvers list
"""
from __future__ import annotations

import pytest
import tempfile
import pathlib
import yaml

from contracts.task import TaskRequest, CorrelationContext, Approval
from control_plane.engine import Engine, WorkflowState, GovernanceControlUnavailable
from control_plane.store import Store


FIXED_TS = "2026-08-27T18:00:00Z"


def _make_engine(tmp_path):
    store = Store(db_path=str(tmp_path / "wf.db"))
    engine = Engine(store=store, audit_db_path=str(tmp_path / "audit.db"))
    # Register handlers for capabilities used in tests.
    engine.register_handler("wfm_forecast", lambda wf: {"ok": True})
    engine.register_handler("pipeline_management", lambda wf: {"ok": True})
    engine.register_handler("ops_execution", lambda wf: {"ok": True})
    return engine


def _make_workflow_request(
    capability="ops_execution",
    owning_role_id="ops_gm",
    requesting_actor="suby",
    input_payload=None,
):
    if input_payload is None:
        input_payload = {}
    corr = CorrelationContext(
        correlation_id=f"corr_{capability}_{owning_role_id}",
        idempotency_key=f"idem_{capability}_{owning_role_id}",
        tenant_id="helix-prime",
        client_id="Account Alpha",
        created_at=FIXED_TS,
    )
    return TaskRequest(
        request_id=f"req_{capability}",
        correlation=corr,
        requesting_actor=requesting_actor,
        owning_role_id=owning_role_id,
        capability=capability,
        input_payload=input_payload,
        requires_approval=True,
        status="proposed",
        created_at=FIXED_TS,
        client_id="Account Alpha",
    )


def _make_approval(actor, role_id="sami", correlation_id="corr-test", subject_id="wf1"):
    return Approval(
        approval_id=f"ap_{actor}_{role_id}",
        correlation_id=correlation_id,
        subject_id=subject_id,
        approver_actor=actor,
        approver_role_id=role_id,
        decision="approved",
        reason="test",
        timestamp=FIXED_TS,
    )


class TestSodIntegrity:
    """Fail-closed SOD checks in Engine.approve."""

    def test_unknown_approver_role_denied(self, tmp_path):
        """An approver role not in the catalog raises GovernanceControlUnavailable."""
        eng = _make_engine(tmp_path)
        wf = eng.submit(_make_workflow_request())
        assert wf.state == WorkflowState.AWAITING_APPROVAL
        appr = _make_approval("unknown_actor", role_id="unknown_role",
                              correlation_id=wf.correlation.correlation_id,
                              subject_id=wf.workflow_id)
        with pytest.raises((ValueError, GovernanceControlUnavailable)):
            eng.approve(wf.workflow_id, appr)

    def test_no_hardcoded_super_role_literals_in_approve(self):
        """Assert that control_plane/engine.py does not contain hardcoded sami/compliance
        super-role literals in the approve() method's SOD check section."""
        import inspect
        from control_plane.engine import Engine
        src = inspect.getsource(Engine.approve)
        assert '"sami"' not in src, "Found hardcoded 'sami' literal in Engine.approve"
        assert "'sami'" not in src, "Found hardcoded 'sami' literal in Engine.approve"
        assert "compliance_quality_gm" not in src, "Found hardcoded compliance_quality_gm in Engine.approve"

    def test_sami_approves_ops_gm_workflow(self, tmp_path):
        """With the default catalog, sami (a universal approver) can approve ops_gm workflows."""
        eng = _make_engine(tmp_path)
        wf = eng.submit(_make_workflow_request(owning_role_id="ops_gm", capability="ops_execution"))
        assert wf.state == WorkflowState.AWAITING_APPROVAL
        appr = _make_approval("sami", role_id="sami",
                              correlation_id=wf.correlation.correlation_id,
                              subject_id=wf.workflow_id)
        result = eng.approve(wf.workflow_id, appr)
        assert result.state == WorkflowState.EXECUTING

    def test_compliance_gm_approves_ops_gm_workflow(self, tmp_path):
        """With the default catalog, compliance_quality_gm can approve ops_gm workflows."""
        eng = _make_engine(tmp_path)
        wf = eng.submit(_make_workflow_request(owning_role_id="ops_gm", capability="ops_execution"))
        assert wf.state == WorkflowState.AWAITING_APPROVAL
        appr = _make_approval("andy", role_id="compliance_quality_gm",
                              correlation_id=wf.correlation.correlation_id,
                              subject_id=wf.workflow_id)
        result = eng.approve(wf.workflow_id, appr)
        assert result.state == WorkflowState.EXECUTING

    def test_super_role_authority_comes_from_catalog(self, tmp_path):
        """Remove sami from universal_approvers AND from ops_gm's can_review list
        in a temp catalog, and verify sami can no longer approve ops_gm workflows."""
        catalog_path = pathlib.Path("organization/role-catalog.yaml")
        original = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
        modified = dict(original)
        modified["universal_approvers"] = []  # remove all universal approvers
        # Also remove sami's ability to review ops_gm (remove ops_gm from sami's can_review)
        for role in modified["roles"]:
            sod = role.get("segregation_of_duties", {})
            can_review = sod.get("can_review", [])
            if "sami" in can_review:
                can_review.remove("sami")
                sod["can_review"] = can_review
            # Also remove ops_gm from sami's can_review list
            if role["id"] == "sami" and "ops_gm" in can_review:
                can_review.remove("ops_gm")
                sod["can_review"] = can_review
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False, encoding="utf-8") as f:
            yaml.dump(modified, f)
            tmp_catalog = f.name
        try:
            from organization.role_catalog import load_role_catalog
            loaded = load_role_catalog(tmp_catalog)
            eng = _make_engine(tmp_path)
            eng.catalog = loaded
            wf = eng.submit(_make_workflow_request(owning_role_id="ops_gm", capability="ops_execution"))
            assert wf.state == WorkflowState.AWAITING_APPROVAL
            # sami is no longer a universal approver and no longer in can_review for ops_gm;
            # ops_gm requires compliance_quality_gm review, so sami is denied.
            appr = _make_approval("sami", role_id="sami",
                                  correlation_id=wf.correlation.correlation_id,
                                  subject_id=wf.workflow_id)
            with pytest.raises((ValueError, GovernanceControlUnavailable)):
                eng.approve(wf.workflow_id, appr)
        finally:
            import os
            os.unlink(tmp_catalog)
