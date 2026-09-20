"""
Phase 4 (A3) — segregation of duties is implemented once.

Eight call sites across seven layers used to carry their own copy of the rule:
the C1 action contract, the C2 workflow engine, the governed workflow manager,
the C3 capability authorizer, the connector write gate, the cockpit approval
preview, the metacognition improvement ledger, and the pilot approval loop.

These tests do four things:

1. They pin the shared predicates themselves.
2. They prove each editable call site's verdict is *driven* by the shared
   predicate, by replacing the site's own binding of it and showing the verdict
   moves. A site that had kept a private copy would not move.
3. They pin the two things unification deliberately did **not** change: the
   governed workflow manager has never forbidden same-role approval, and
   ``pilot/approval.py`` is a frozen deployed artifact whose verdicts must keep
   matching the shared predicates without being edited.
4. They stop the duplication from growing back, with an AST guard rather than a
   text search, so prose in a docstring cannot trip it.
"""
from __future__ import annotations

import ast
import pathlib
import sys
import uuid

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
# `cockpit/` has no `__init__.py` and ships a `cockpit.py` of its own, so its
# modules import flat, matching the repo convention (see
# tests/test_command_center_integration.py). Importing it as `cockpit.x` works
# only until another test puts `cockpit/` on sys.path, then it stops resolving.
sys.path.insert(0, str(REPO_ROOT / "cockpit"))
sys.path.insert(0, str(REPO_ROOT))

from command_center_integration import evaluate_approval  # noqa: E402

from connectors.base import BaseConnector  # noqa: E402
from connectors.contracts import ConnectorContext  # noqa: E402
from contracts.segregation_of_duties import (  # noqa: E402
    SOD_SAME_ROLE,
    SOD_SELF_APPROVAL,
    SOD_UNAUTHORIZED_PEER,
    SOD_UNAUTHORIZED_REVIEWER,
    SOD_VIOLATIONS,
    approval_sod_verdict,
    approval_violation,
    declared_peer_calls,
    declared_review_scope,
    declared_reviewers,
    is_universal_approver,
    peer_authority_violation,
    reviewer_authority_violation,
    same_role_violation,
    self_approval_violation,
)
from contracts.task import Action, Approval, CorrelationContext  # noqa: E402
from control_plane.engine import Engine, GovernanceControlUnavailable  # noqa: E402
from control_plane.governance import (  # noqa: E402
    CorrelationContext as GovernanceCorrelationContext,
)
from control_plane.governance import (  # noqa: E402
    GovernanceStateError,
    GovernedWorkflowManager,
)
from control_plane.governance import (  # noqa: E402
    TaskRequest as GovernanceTaskRequest,
)
from control_plane.store import Store as GovernanceStore  # noqa: E402
from control_plane.workflow import WorkflowState  # noqa: E402
from metacognition.improvement import EVALUATED, MetacognitionEngine  # noqa: E402
from organization.role_catalog import load_role_catalog
from pilot.approval import evaluate_approval_decision
from security.identity import Identity
from security.policy import AuthorizationRequest, authorize

TS = "2026-09-20T00:00:00Z"

#: Modules allowed to contain a hand-rolled SOD equality comparison: the one
#: implementation, and the frozen pilot loop that is pinned rather than edited.
SOD_DECLARATION_SITES = {
    "contracts/segregation_of_duties.py",
    "pilot/approval.py",
}

#: Repository roots scanned by the anti-duplication guard.
SCAN_ROOTS = (
    "app",
    "capabilities",
    "cloud",
    "cockpit",
    "connectors",
    "contracts",
    "control_plane",
    "customer_success",
    "demo",
    "engines",
    "helix_codex_app",
    "integrations",
    "memory",
    "metacognition",
    "organization",
    "pilot",
    "release",
    "security",
    "server",
)

#: A comparison counts as a hand-rolled SOD rule when one side names an approver
#: and the other names the party whose work is being approved.
_SUBJECT_TOKENS = ("actor", "requester", "owning", "owner")


# ── builders ───────────────────────────────────────────────────────────────


def _corr(cid: str = "corr-sod") -> CorrelationContext:
    return CorrelationContext(
        correlation_id=cid,
        idempotency_key="idem-sod",
        tenant_id="helix-prime",
        client_id="Account Alpha",
        created_at=TS,
    )


def _approval(
    *,
    actor: str,
    role: str,
    cid: str = "corr-sod",
    subject: str = "act-1",
    decision: str = "approved",
) -> Approval:
    return Approval(
        approval_id=f"ap-{actor}-{role}",
        correlation_id=cid,
        subject_id=subject,
        approver_actor=actor,
        approver_role_id=role,
        decision=decision,
        reason="test",
        timestamp=TS,
    )


def _action(
    *,
    actor: str = "suby",
    owning_role: str = "ops_gm",
    approver_actor: str = "sami",
    approver_role: str = "sami",
    capability: str = "wfm_forecast",
) -> Action:
    return Action(
        action_id="act-1",
        correlation=_corr(),
        tenant_id="helix-prime",
        client_id="Account Alpha",
        actor=actor,
        owning_role_id=owning_role,
        capability=capability,
        payload={},
        requires_approval=True,
        status="proposed",
        created_at=TS,
        approval=_approval(actor=approver_actor, role=approver_role),
    )


def _engine(tmp_path) -> Engine:
    from control_plane.store import Store

    eng = Engine(store=Store(db_path=str(tmp_path / "wf.db")), audit_db_path=str(tmp_path / "a.db"))
    eng.register_handler("ops_execution", lambda wf: {"ok": True})
    return eng


def _engine_workflow(eng: Engine, *, actor: str = "suby", owning_role: str = "ops_gm"):
    corr = CorrelationContext(
        correlation_id="corr-engine",
        idempotency_key="idem-engine",
        tenant_id="helix-prime",
        client_id="Account Alpha",
        created_at=TS,
    )
    return eng.submit(
        GovernanceTaskRequest(
            request_id="req-engine",
            correlation=corr,
            requesting_actor=actor,
            owning_role_id=owning_role,
            capability="ops_execution",
            input_payload={},
            requires_approval=True,
            status="proposed",
            created_at=TS,
            client_id="Account Alpha",
        )
    )


def _gov_manager(tmp_path) -> GovernedWorkflowManager:
    return GovernedWorkflowManager(store=GovernanceStore(db_path=str(tmp_path / "gov.db")))


def _gov_request(
    *,
    actor: str = "suby",
    role: str = "ops_gm",
    cost: float = 100.0,
    requires_approval: bool = True,
):
    """A request that lands in ``awaiting_approval``.

    ``requires_approval=True`` freezes the task regardless of cost, which keeps
    the approver's own financial ceiling out of the way of the SOD verdicts
    these tests are about.
    """
    return GovernanceTaskRequest(
        request_id="req-gov",
        correlation=GovernanceCorrelationContext(
            correlation_id=str(uuid.uuid4()),
            idempotency_key=str(uuid.uuid4()),
            tenant_id="helix-prime",
            client_id="Account Alpha",
            created_at=TS,
            actor_id=actor,
        ),
        requesting_actor=actor,
        owning_role_id=role,
        capability="wfm_forecast",
        input_payload={"client": "Account Alpha", "estimated_financial_cost": cost},
        requires_approval=requires_approval,
        status="proposed",
        created_at=TS,
        tenant_id="helix-prime",
        client_id="Account Alpha",
        target_engine="wfm",
        estimated_financial_cost=cost,
        confidence_score=0.95,
        requested_data_classification="internal",
    )


def _catalog():
    catalog = load_role_catalog()
    return catalog["roles_by_id"], catalog["universal_approvers"]


def _cockpit_view(*, actor: str = "operator", role_id: str = "ict_gm", required_role: str):
    return type(
        "View",
        (),
        {
            "meta": type("Meta", (), {"actor": actor, "role_id": role_id})(),
            "approval_preview": type("Preview", (), {"required": True, "role": required_role})(),
        },
    )()


# ── the shared predicates ──────────────────────────────────────────────────


class TestSharedPredicates:
    """The one implementation, tested on its own terms."""

    def test_violation_codes_are_distinct(self):
        assert len(set(SOD_VIOLATIONS)) == 4
        assert SOD_SELF_APPROVAL in SOD_VIOLATIONS
        assert SOD_SAME_ROLE in SOD_VIOLATIONS
        assert SOD_UNAUTHORIZED_REVIEWER in SOD_VIOLATIONS
        assert SOD_UNAUTHORIZED_PEER in SOD_VIOLATIONS

    @pytest.mark.parametrize(
        "actor,approver,expected",
        [
            ("suby", "suby", True),
            ("suby", "sami", False),
            ("", "", True),
            ("suby", "SUBZ", False),
        ],
    )
    def test_self_approval(self, actor, approver, expected):
        assert self_approval_violation(actor, approver) is expected

    @pytest.mark.parametrize(
        "owning,approver,expected",
        [
            ("ops_gm", "ops_gm", True),
            ("ops_gm", "sami", False),
            ("ops_gm", "", False),
        ],
    )
    def test_same_role(self, owning, approver, expected):
        assert same_role_violation(owning, approver) is expected

    def test_approval_violation_reports_identity_before_role(self):
        assert approval_violation("suby", "suby", "ops_gm", "ops_gm") == SOD_SELF_APPROVAL

    def test_approval_violation_can_decline_to_enforce_same_role(self):
        """The governed workflow manager's scope, expressed as a parameter."""
        assert approval_violation("suby", "wili", "ops_gm", "ops_gm") == SOD_SAME_ROLE
        assert (
            approval_violation("suby", "wili", "ops_gm", "ops_gm", enforce_same_role=False) is None
        )

    def test_clean_pair_is_clean(self):
        assert approval_violation("suby", "sami", "ops_gm", "sami") is None

    def test_universal_approver_membership(self):
        assert is_universal_approver(["sami", "compliance_quality_gm"], "sami") is True
        assert is_universal_approver(["sami"], "ops_gm") is False

    def test_declared_helpers_read_the_catalog(self):
        roles, _ = _catalog()
        assert declared_reviewers(roles, "ops_gm") == ["compliance_quality_gm"]
        assert declared_review_scope(roles, "ops_gm") == []
        assert "sami" in declared_peer_calls(roles, "ops_gm")

    def test_declared_helpers_tolerate_absent_roles(self):
        assert declared_reviewers({}, "ghost") == []
        assert declared_review_scope({}, "ghost") == []
        assert declared_peer_calls({}, "ghost") == []

    def test_reviewer_authority(self):
        roles, universal = _catalog()
        # sami is a universal approver.
        assert reviewer_authority_violation(roles, universal, "ops_gm", "sami") is False
        # compliance_quality_gm is named in ops_gm's must_be_reviewed_by.
        assert (
            reviewer_authority_violation(roles, universal, "ops_gm", "compliance_quality_gm")
            is False
        )
        # the owning role is not authorised to review itself.
        assert reviewer_authority_violation(roles, universal, "ops_gm", "ops_gm") is True
        # an unknown role is never authorised.
        assert reviewer_authority_violation(roles, universal, "ops_gm", "ghost") is True

    def test_reviewer_authority_honours_can_review(self):
        roles = {
            "owning": {"segregation_of_duties": {"must_be_reviewed_by": []}},
            "reviewer": {"segregation_of_duties": {"can_review": ["owning"]}},
        }
        assert reviewer_authority_violation(roles, [], "owning", "reviewer") is False

    def test_peer_authority(self):
        roles, universal = _catalog()
        # a role always acts on its own capability.
        assert peer_authority_violation(roles, universal, "ops_gm", "ops_gm") is False
        # ops_gm declares compliance_quality_gm a peer.
        assert (
            peer_authority_violation(roles, universal, "ops_gm", "compliance_quality_gm") is False
        )
        # ops_gm does not declare sales_gm a peer.
        assert peer_authority_violation(roles, universal, "ops_gm", "sales_gm") is True
        # a universal approver may act on anything.
        assert peer_authority_violation(roles, universal, "sami", "sales_gm") is False

    def test_peer_authority_fails_closed_on_an_empty_catalog(self):
        assert peer_authority_violation({}, [], "ops_gm", "sales_gm") is True

    def test_whole_verdict_combines_identity_and_authority(self):
        roles, universal = _catalog()
        assert (
            approval_sod_verdict(
                roles_by_id=roles,
                universal_approvers=universal,
                actor="suby",
                approver_actor="sami",
                owning_role_id="ops_gm",
                approver_role_id="sami",
            )
            is None
        )
        assert (
            approval_sod_verdict(
                roles_by_id=roles,
                universal_approvers=universal,
                actor="suby",
                approver_actor="sami",
                owning_role_id="ops_gm",
                approver_role_id="ghost",
            )
            == SOD_UNAUTHORIZED_REVIEWER
        )

    def test_malformed_sod_block_yields_a_verdict_instead_of_a_crash(self):
        """A recorded hardening: ``must_be_reviewed_by: null`` used to raise TypeError."""
        roles = {"owning": {"segregation_of_duties": {"must_be_reviewed_by": None}}}
        assert reviewer_authority_violation(roles, [], "owning", "ghost") is True


# ── site 1: the C1 action contract ─────────────────────────────────────────


class TestActionContract:
    def test_clean_pair_is_accepted(self):
        assert _action(actor="suby", approver_actor="sami", approver_role="sami") is not None

    def test_self_approval_is_refused(self):
        with pytest.raises(ValueError, match="self-approval forbidden"):
            _action(actor="suby", approver_actor="suby", approver_role="sami")

    def test_same_role_approval_is_refused(self):
        with pytest.raises(ValueError, match="SOD violation"):
            _action(actor="suby", approver_actor="wili", approver_role="ops_gm")

    def test_delegates_to_the_shared_predicate(self, monkeypatch):
        monkeypatch.setattr("contracts.task.approval_violation", lambda *a, **k: SOD_SAME_ROLE)
        with pytest.raises(ValueError, match="SOD violation"):
            _action(actor="suby", approver_actor="sami", approver_role="sami")

    def test_can_fail_when_the_predicate_is_neutralised(self, monkeypatch):
        monkeypatch.setattr("contracts.task.approval_violation", lambda *a, **k: None)
        action = _action(actor="suby", approver_actor="suby", approver_role="ops_gm")
        assert action.approval.approver_actor == "suby"


# ── site 2: the C2 workflow engine ─────────────────────────────────────────


class TestWorkflowEngine:
    def test_universal_approver_is_accepted(self, tmp_path):
        eng = _engine(tmp_path)
        wf = _engine_workflow(eng)
        assert wf.state == WorkflowState.AWAITING_APPROVAL
        result = eng.approve(
            wf.workflow_id,
            _approval(
                actor="sami", role="sami", subject=wf.workflow_id, cid=wf.correlation.correlation_id
            ),
        )
        assert result.state == WorkflowState.EXECUTING

    def test_self_approval_is_refused(self, tmp_path):
        eng = _engine(tmp_path)
        wf = _engine_workflow(eng, actor="suby")
        with pytest.raises(ValueError, match="self-approval forbidden"):
            eng.approve(
                wf.workflow_id,
                _approval(
                    actor="suby",
                    role="sami",
                    subject=wf.workflow_id,
                    cid=wf.correlation.correlation_id,
                ),
            )

    def test_same_role_approval_is_refused(self, tmp_path):
        eng = _engine(tmp_path)
        wf = _engine_workflow(eng, actor="suby", owning_role="ops_gm")
        with pytest.raises(ValueError, match="same-role approval forbidden"):
            eng.approve(
                wf.workflow_id,
                _approval(
                    actor="wili",
                    role="ops_gm",
                    subject=wf.workflow_id,
                    cid=wf.correlation.correlation_id,
                ),
            )

    def test_unauthorised_reviewer_is_refused(self, tmp_path):
        eng = _engine(tmp_path)
        wf = _engine_workflow(eng, owning_role="ops_gm")
        with pytest.raises((ValueError, GovernanceControlUnavailable)):
            eng.approve(
                wf.workflow_id,
                _approval(
                    actor="ghost",
                    role="ghost",
                    subject=wf.workflow_id,
                    cid=wf.correlation.correlation_id,
                ),
            )

    def test_identity_check_delegates(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "control_plane.engine.approval_violation", lambda *a, **k: SOD_SELF_APPROVAL
        )
        eng = _engine(tmp_path)
        wf = _engine_workflow(eng)
        with pytest.raises(ValueError, match="self-approval forbidden"):
            eng.approve(
                wf.workflow_id,
                _approval(
                    actor="sami",
                    role="sami",
                    subject=wf.workflow_id,
                    cid=wf.correlation.correlation_id,
                ),
            )

    def test_authority_check_delegates(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "control_plane.engine.reviewer_authority_violation", lambda *a, **k: True
        )
        eng = _engine(tmp_path)
        wf = _engine_workflow(eng)
        with pytest.raises(ValueError, match="not authorized to approve"):
            eng.approve(
                wf.workflow_id,
                _approval(
                    actor="sami",
                    role="sami",
                    subject=wf.workflow_id,
                    cid=wf.correlation.correlation_id,
                ),
            )


# ── site 3: the governed workflow manager ──────────────────────────────────


class TestGovernedWorkflowManager:
    def test_self_approval_is_refused(self, tmp_path):
        mgr = _gov_manager(tmp_path)
        record = mgr.submit(_gov_request(actor="suby"))
        with pytest.raises(GovernanceStateError, match="segregation of duties"):
            mgr.approve(record.task_id, "suby")

    def test_self_approval_check_delegates(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "control_plane.governance.self_approval_violation", lambda *a, **k: True
        )
        mgr = _gov_manager(tmp_path)
        record = mgr.submit(_gov_request(actor="suby"))
        with pytest.raises(GovernanceStateError, match="segregation of duties"):
            mgr.approve(record.task_id, "sami")

    def test_can_fail_when_the_predicate_is_neutralised(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "control_plane.governance.self_approval_violation", lambda *a, **k: False
        )
        mgr = _gov_manager(tmp_path)
        record = mgr.submit(_gov_request(actor="suby"))
        # Normally refused; with the shared predicate neutralised the approval proceeds.
        released = mgr.approve(record.task_id, "suby")
        assert released.state == WorkflowState.EXECUTING

    def test_same_role_approval_is_deliberately_allowed_here(self, tmp_path):
        """A pinned scope difference, not a regression.

        The C1 action contract and the C2 engine forbid same-role approval; this
        manager never has, and unifying the predicates did not change that. A
        *different actor* resolving to the owning role is accepted. If a future
        change wants to forbid it, this test is the place to change.
        """
        mgr = _gov_manager(tmp_path)
        record = mgr.submit(_gov_request(actor="suby", role="ops_gm"))
        # "ops_gm" is a catalog role id, so it resolves as an actor holding ops_gm.
        released = mgr.approve(record.task_id, "ops_gm")
        assert released.state == WorkflowState.EXECUTING

    def test_different_actor_approval_is_accepted(self, tmp_path):
        mgr = _gov_manager(tmp_path)
        record = mgr.submit(_gov_request(actor="suby"))
        released = mgr.approve(record.task_id, "sami")
        assert released.state == WorkflowState.EXECUTING


# ── site 4: the C3 capability authorizer ───────────────────────────────────


def _authorize(role_id: str, capability: str):
    return authorize(
        AuthorizationRequest(
            identity=Identity(actor="someone", actor_type="human", role_id=role_id),
            capability=capability,
        )
    )


class TestCapabilityAuthorizer:
    def test_owner_may_act_on_its_own_capability(self):
        assert _authorize("ops_gm", "wfm_forecast").allowed is True

    def test_declared_peer_may_act(self):
        # ops_gm declares compliance_quality_gm a peer, and wfm_forecast is ops_gm's.
        assert _authorize("compliance_quality_gm", "wfm_forecast").allowed is True

    def test_undeclared_peer_is_denied(self):
        decision = _authorize("marketing_gm", "wfm_forecast")
        assert decision.allowed is False
        assert decision.code == "unauthorized_role"

    def test_universal_approver_may_act(self):
        assert _authorize("sami", "wfm_forecast").allowed is True

    def test_peer_check_delegates(self, monkeypatch):
        monkeypatch.setattr("security.policy.peer_authority_violation", lambda *a, **k: True)
        decision = _authorize("sami", "wfm_forecast")
        assert decision.allowed is False
        assert decision.code == "unauthorized_role"

    def test_can_fail_when_the_predicate_is_neutralised(self, monkeypatch):
        monkeypatch.setattr("security.policy.peer_authority_violation", lambda *a, **k: False)
        assert _authorize("marketing_gm", "wfm_forecast").allowed is True


# ── site 5: the connector write gate ───────────────────────────────────────


class TestConnectorWriteGate:
    @staticmethod
    def _context(actor: str = "codex") -> ConnectorContext:
        return ConnectorContext(
            tenant_id="helix-prime",
            organization_id="scoach",
            client_id="Account Alpha",
            actor=actor,
        )

    @staticmethod
    def _approval(actor: str, role: str = "ops_gm", decision: str = "approved"):
        return type(
            "Approval",
            (),
            {"approver_actor": actor, "approver_role_id": role, "decision": decision},
        )()

    def test_cross_actor_approval_is_valid(self):
        assert BaseConnector._approval_valid(self._approval("sami"), self._context("codex")) is True

    def test_self_approval_is_invalid(self):
        assert (
            BaseConnector._approval_valid(self._approval("codex"), self._context("codex")) is False
        )

    def test_missing_approval_is_invalid(self):
        assert BaseConnector._approval_valid(None, self._context()) is False

    def test_unapproved_decision_is_invalid(self):
        approval = self._approval("sami", decision="denied")
        assert BaseConnector._approval_valid(approval, self._context("codex")) is False

    def test_self_approval_check_delegates(self, monkeypatch):
        monkeypatch.setattr("connectors.base.self_approval_violation", lambda *a, **k: True)
        assert (
            BaseConnector._approval_valid(self._approval("sami"), self._context("codex")) is False
        )


# ── site 6: the cockpit approval preview ───────────────────────────────────


class TestCockpitApprovalPreview:
    def test_cross_role_approval_is_allowed(self):
        view = _cockpit_view(role_id="ict_gm", required_role="customer_success_gm")
        decision = evaluate_approval(
            view, approver_actor="bob", approver_role_id="customer_success_gm"
        )
        assert decision.decision == "allowed"

    def test_self_approval_is_denied(self):
        view = _cockpit_view(
            actor="operator", role_id="customer_success_gm", required_role="customer_success_gm"
        )
        decision = evaluate_approval(
            view, approver_actor="operator", approver_role_id="customer_success_gm"
        )
        assert decision.decision == "denied"
        assert "self-approval" in decision.reason.lower()

    def test_same_role_approval_is_denied(self):
        view = _cockpit_view(role_id="ict_gm", required_role="customer_success_gm")
        decision = evaluate_approval(view, approver_actor="bob", approver_role_id="ict_gm")
        assert decision.decision == "denied"
        assert "same-role" in decision.reason.lower()

    def test_required_role_rule_is_still_local(self):
        view = _cockpit_view(role_id="ict_gm", required_role="customer_success_gm")
        decision = evaluate_approval(view, approver_actor="bob", approver_role_id="marketing_gm")
        assert decision.decision == "denied"
        assert "not authorized" in decision.reason

    def test_self_approval_check_delegates(self, monkeypatch):
        monkeypatch.setattr(
            "command_center_integration.approval_violation",
            lambda *a, **k: SOD_SELF_APPROVAL,
        )
        view = _cockpit_view(role_id="ict_gm", required_role="customer_success_gm")
        decision = evaluate_approval(
            view, approver_actor="bob", approver_role_id="customer_success_gm"
        )
        assert decision.decision == "denied"
        assert "self-approval" in decision.reason.lower()

    def test_can_fail_when_the_predicate_is_neutralised(self, monkeypatch):
        monkeypatch.setattr("command_center_integration.approval_violation", lambda *a, **k: None)
        view = _cockpit_view(
            actor="operator", role_id="customer_success_gm", required_role="customer_success_gm"
        )
        decision = evaluate_approval(
            view, approver_actor="operator", approver_role_id="customer_success_gm"
        )
        assert decision.decision == "allowed"


# ── site 7: the metacognition improvement ledger ───────────────────────────


def _metacognition_proposal(tmp_path) -> MetacognitionEngine:
    eng = MetacognitionEngine(path=str(tmp_path / "prop.jsonl"))
    proposal = eng.propose(
        kind="policy",
        target="approval_threshold",
        baseline="threshold=0.5",
        proposed="threshold=0.3",
        baseline_policy={"value": 0.5},
        proposed_policy={"value": 0.3},
        hypothesis="lower threshold improves throughput",
        evidence=["rec-0001"],
        risk_assessment="low: reversible",
        rollback_plan="restore previous threshold",
        tenant_id="t1",
        client_id="c1",
        created_by="agent-1",
        role_id="customer_success_gm",
        correlation_id="corr-meta",
        timestamp=TS,
        min_improvement=0.0,
    )

    def simulate(policy, case):
        return case.get("score", 0.0) >= policy.get("value", 1.0)

    cases = [{"score": s} for s in (0.2, 0.4, 0.6, 0.8)]
    eng.evaluate(proposal, historical_cases=cases, simulated_cases=cases, simulate=simulate)
    assert eng.get_proposal(proposal.proposal_id).approval_state == EVALUATED
    return eng, proposal


class TestMetacognitionApproval:
    def test_cross_role_approval_is_allowed(self, tmp_path):
        eng, proposal = _metacognition_proposal(tmp_path)
        decision = eng.approve(proposal.proposal_id, "human-1", "ict_gm")
        assert decision.decision == "allowed"

    def test_self_approval_is_denied(self, tmp_path):
        eng, proposal = _metacognition_proposal(tmp_path)
        decision = eng.approve(proposal.proposal_id, "agent-1", "ict_gm", requester_actor="agent-1")
        assert decision.decision == "denied"
        assert "self-approval" in decision.reason.lower()

    def test_same_role_approval_is_denied(self, tmp_path):
        eng, proposal = _metacognition_proposal(tmp_path)
        decision = eng.approve(proposal.proposal_id, "human-2", "customer_success_gm")
        assert decision.decision == "denied"
        assert "same-role" in decision.reason.lower()

    def test_self_approval_check_delegates(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "metacognition.improvement.approval_violation", lambda *a, **k: SOD_SELF_APPROVAL
        )
        eng, proposal = _metacognition_proposal(tmp_path)
        decision = eng.approve(proposal.proposal_id, "human-1", "ict_gm")
        assert decision.decision == "denied"
        assert "self-approval" in decision.reason.lower()

    def test_can_fail_when_the_predicate_is_neutralised(self, monkeypatch, tmp_path):
        monkeypatch.setattr("metacognition.improvement.approval_violation", lambda *a, **k: None)
        eng, proposal = _metacognition_proposal(tmp_path)
        decision = eng.approve(proposal.proposal_id, "human-2", "customer_success_gm")
        assert decision.decision == "allowed"


# ── the frozen site: the pilot approval loop ───────────────────────────────


class TestFrozenPilotLoop:
    """``pilot/`` is a deployed artifact, so it is pinned rather than edited.

    These tests assert its verdicts are the shared predicates' verdicts. If the
    two ever diverge, CI fails here instead of the difference going unnoticed.
    """

    @pytest.mark.parametrize(
        "actor,approver_actor,owning_role,approver_role",
        [
            ("suby", "suby", "ops_gm", "ops_gm"),
            ("suby", "sami", "ops_gm", "ops_gm"),
            ("suby", "wili", "ops_gm", "ld_gm"),
            ("suby", "wili", "ops_gm", "ops_gm"),
            ("suby", "sami", "ops_gm", "sami"),
        ],
    )
    def test_verdict_matches_the_shared_predicate(
        self, actor, approver_actor, owning_role, approver_role
    ):
        allowed, reason = evaluate_approval_decision(
            None, "approved", approver_actor, approver_role, actor, owning_role
        )
        expected = approval_violation(actor, approver_actor, owning_role, approver_role)
        assert allowed is (expected is None), reason

    def test_denied_decision_short_circuits(self):
        allowed, reason = evaluate_approval_decision(
            None, "denied", "sami", "sami", "suby", "ops_gm"
        )
        assert allowed is True
        assert reason == "denied"

    def test_self_approval_reason_matches_the_shared_violation(self):
        allowed, reason = evaluate_approval_decision(
            None, "approved", "suby", "sami", "suby", "ops_gm"
        )
        assert allowed is False
        assert "self-approval" in reason
        assert approval_violation("suby", "suby", "ops_gm", "sami") == SOD_SELF_APPROVAL

    def test_same_role_reason_matches_the_shared_violation(self):
        allowed, reason = evaluate_approval_decision(
            None, "approved", "wili", "ops_gm", "suby", "ops_gm"
        )
        assert allowed is False
        assert "same-role" in reason
        assert approval_violation("suby", "wili", "ops_gm", "ops_gm") == SOD_SAME_ROLE


# ── anti-duplication guard ─────────────────────────────────────────────────


def _sod_shaped_comparisons(
    repo_root: pathlib.Path = REPO_ROOT,
    roots: tuple[str, ...] = SCAN_ROOTS,
) -> dict[str, list[int]]:
    """Modules containing a hand-rolled ``approver == subject`` comparison."""
    found: dict[str, list[int]] = {}
    for root in roots:
        base = repo_root / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Compare):
                    continue
                if not any(isinstance(op, ast.Eq) for op in node.ops):
                    continue
                if len(node.comparators) != 1:
                    continue
                left = _operand_names(node.left)
                right = _operand_names(node.comparators[0])
                if (_names_approver(left) and _names_subject(right)) or (
                    _names_approver(right) and _names_subject(left)
                ):
                    found.setdefault(path.relative_to(repo_root).as_posix(), []).append(node.lineno)
    return found


def _operand_names(node: ast.expr) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            names.add(child.id.lower())
        elif isinstance(child, ast.Attribute):
            names.add(child.attr.lower())
    return names


def _names_approver(names: set[str]) -> bool:
    return any("approver" in name for name in names)


def _names_subject(names: set[str]) -> bool:
    return any(token in name for name in names for token in _SUBJECT_TOKENS)


class TestSingleDeclaration:
    def test_only_the_shared_module_and_the_frozen_pilot_implement_the_rule(self):
        found = _sod_shaped_comparisons()
        assert set(found) == SOD_DECLARATION_SITES, (
            "a hand-rolled segregation-of-duties comparison appeared or disappeared; "
            f"expected {sorted(SOD_DECLARATION_SITES)}, found {sorted(found)}"
        )

    def test_the_guard_can_fail(self, tmp_path):
        """Proof the guard above is not vacuous."""
        module = tmp_path / "contracts"
        module.mkdir()
        (module / "offender.py").write_text(
            "def check(approver_actor, actor):\n" "    return approver_actor == actor\n",
            encoding="utf-8",
        )
        assert set(_sod_shaped_comparisons(tmp_path, ("contracts",))) == {"contracts/offender.py"}

    def test_the_guard_ignores_prose(self, tmp_path):
        """A docstring that says ``approver == requester`` is not an implementation."""
        module = tmp_path / "contracts"
        module.mkdir()
        (module / "prose.py").write_text(
            '"""Self-approval (approver == requester actor) is denied."""\n'
            "def check():\n    return None\n",
            encoding="utf-8",
        )
        assert _sod_shaped_comparisons(tmp_path, ("contracts",)) == {}

    def test_every_editable_site_imports_the_shared_module(self):
        """Delegation is structural, not incidental: each site names the module."""
        sites = {
            "contracts/task.py",
            "control_plane/engine.py",
            "control_plane/governance.py",
            "security/policy.py",
            "connectors/base.py",
            "cockpit/command_center_integration.py",
            "metacognition/improvement.py",
        }
        for site in sorted(sites):
            source = (REPO_ROOT / site).read_text(encoding="utf-8")
            assert "contracts.segregation_of_duties" in source, f"{site} does not import the module"
